"""Google Hotels Prices & OTA Rate Tracker - Apify Actor entry point."""

from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from apify import Actor

from .gh_client import GoogleHotelsClient, SearchContext, build_hotel_url, extract_entity, google_query_url

EVENT_LISTING = "hotel-listing"   # row from search results only (lowest price + hotel data)
EVENT_OFFERS = "hotel-offers"     # row with every OTA / official-site offer for that hotel and date


class ChargeLimitReached(Exception):
    pass


def parse_date(value: Any, today: date) -> date:
    """Accepts YYYY-MM-DD, 'today', 'tomorrow', '+14', '+14 days', '2 weeks', '1 month'."""
    if value in (None, ""):
        return today + timedelta(days=14)
    s = str(value).strip().lower()
    if s == "today":
        return today
    if s == "tomorrow":
        return today + timedelta(days=1)
    m = re.fullmatch(r"\+?\s*(\d+)\s*(d|day|days|w|week|weeks|m|month|months)?", s)
    if m:
        n, unit = int(m.group(1)), (m.group(2) or "d")[0]
        return today + timedelta(days=n * {"d": 1, "w": 7, "m": 30}[unit])
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


class Runner:
    def __init__(self, inp: dict, client: GoogleHotelsClient) -> None:
        self.inp = inp
        self.client = client
        self.include_offers = bool(inp.get("includeOtaOffers", True))
        self.include_rooms = bool(inp.get("includeRoomTypes", False)) and self.include_offers
        self.event = EVENT_OFFERS if self.include_offers else EVENT_LISTING
        self.sem = asyncio.Semaphore(max(1, min(int(inp.get("maxConcurrency", 5)), 20)))
        self.stop = False
        self.pushed = 0
        self.failed: list[dict] = []
        self.max_items = int(inp.get("maxItems") or 0)

    # ------------------------------------------------------------------ output

    async def push(self, row: dict) -> None:
        if self.stop:
            raise ChargeLimitReached()
        if self.max_items and self.pushed >= self.max_items:
            self.stop = True
            raise ChargeLimitReached()
        result = await Actor.push_data(row, charged_event_name=self.event)
        self.pushed += 1
        if result is not None and result.event_charge_limit_reached:
            Actor.log.info("Maximum cost per run reached, finishing.")
            self.stop = True

    def base_row(self, hotel: dict, ctx: SearchContext) -> dict:
        nights = (ctx.check_out - ctx.check_in).days
        row = {
            "hotelName": hotel.get("hotelName"),
            "hotelId": hotel.get("hotelId"),
            "checkIn": ctx.check_in.isoformat(),
            "checkOut": ctx.check_out.isoformat(),
            "nights": nights,
            "adults": ctx.adults,
            "currency": ctx.currency,
            "lowestPricePerNight": hotel.get("lowestPricePerNight"),
            "lowestPriceProvider": None,
            "lowestTotalPrice": round(hotel["lowestPricePerNight"] * nights, 2)
            if hotel.get("lowestPricePerNight") is not None else None,
        }
        for k in ("rating", "reviewCount", "hotelClass", "hotelType", "address", "phone", "website",
                  "latitude", "longitude", "countryCode", "checkInTime", "checkOutTime", "description",
                  "thumbnailUrl", "googleMapsId"):
            row[k] = hotel.get(k)
        row["googleHotelsUrl"] = build_hotel_url(hotel["hotelId"], hotel.get("hotelName"), ctx,
                                                 self.client.hl, self.client.gl) if hotel.get("hotelId") else None
        return row

    async def emit_hotel(self, hotel: dict, ctx: SearchContext, extra: dict) -> None:
        row = self.base_row(hotel, ctx)
        row.update(extra)
        if self.include_offers:
            async with self.sem:
                if self.stop:
                    return
                try:
                    offers = await self.client.offers(hotel["hotelId"], ctx, self.include_rooms)
                except Exception as err:  # noqa: BLE001
                    self.failed.append({"hotelId": hotel["hotelId"], "checkIn": row["checkIn"], "error": str(err)[:300]})
                    Actor.log.warning(f"Offers failed for {hotel.get('hotelName')} {row['checkIn']}: {err}")
                    return
            if offers.get("lowestPricePerNight") is not None:
                row["lowestPricePerNight"] = offers["lowestPricePerNight"]
                row["lowestTotalPrice"] = round(offers["lowestPricePerNight"] * row["nights"], 2)
            row["lowestPriceProvider"] = offers.get("lowestPriceProvider")
            row["isAvailable"] = bool(offers.get("offersCount"))
            row["offersCount"] = offers.get("offersCount", 0)
            row["offers"] = offers.get("offers", [])
            row["priceInsight"] = offers.get("priceInsight")
            row["stayTotal"] = offers.get("stayTotal")
            if self.include_rooms:
                row["roomTypes"] = offers.get("roomTypes", [])
        else:
            row["isAvailable"] = row["lowestPricePerNight"] is not None
        row["scrapedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        await self.push(row)

    # ------------------------------------------------------------------ modes

    async def run_search(self, query: str, ctx: SearchContext, max_results: int) -> None:
        async with self.sem:
            if self.stop:
                return
            try:
                hotels = await self.client.search(query, ctx, max_results)
            except Exception as err:  # noqa: BLE001
                self.failed.append({"searchQuery": query, "checkIn": ctx.check_in.isoformat(), "error": str(err)[:300]})
                Actor.log.warning(f"Search failed for '{query}' {ctx.check_in}: {err}")
                return
        Actor.log.info(f"'{query}' {ctx.check_in}: {len(hotels)} hotels")
        await asyncio.gather(*(
            self.emit_hotel(h, ctx, {"searchQuery": query, "searchRank": i + 1,
                                     "searchUrl": google_query_url(query, ctx, self.client.hl, self.client.gl)})
            for i, h in enumerate(hotels)
        ), return_exceptions=True)

    async def resolve_hotel(self, value: str, ctx: SearchContext) -> dict | None:
        entity = extract_entity(value)
        async with self.sem:
            if entity:
                hotel = await self.client.lookup(entity, ctx)
                return hotel or {"hotelId": entity}
            found = await self.client.search(value, ctx, 1)
        if not found:
            return None
        found[0]["matchedFromQuery"] = value
        return found[0]

    async def run_hotel(self, value: str, contexts: list[SearchContext]) -> None:
        try:
            hotel = await self.resolve_hotel(value, contexts[0])
        except Exception as err:  # noqa: BLE001
            self.failed.append({"hotel": value, "error": str(err)[:300]})
            Actor.log.warning(f"Could not resolve hotel '{value}': {err}")
            return
        if not hotel:
            self.failed.append({"hotel": value, "error": "No matching hotel found on Google Hotels"})
            Actor.log.warning(f"No Google Hotels match for '{value}'")
            return
        Actor.log.info(f"Hotel '{value}' -> {hotel.get('hotelName')} ({hotel['hotelId']})")

        async def per_date(i: int, ctx: SearchContext) -> None:
            h = hotel
            if not self.include_offers and i > 0:
                # listing mode: refresh the lowest price for this date via a cheap lookup
                async with self.sem:
                    if self.stop:
                        return
                    try:
                        h = await self.client.lookup(hotel["hotelId"], ctx) or hotel
                    except Exception as err:  # noqa: BLE001
                        self.failed.append({"hotelId": hotel["hotelId"], "checkIn": ctx.check_in.isoformat(),
                                            "error": str(err)[:300]})
                        return
                h = {**hotel, "lowestPricePerNight": h.get("lowestPricePerNight")}
            await self.emit_hotel(h, ctx, {"input": value, **({"matchedFromQuery": value}
                                                               if hotel.get("matchedFromQuery") else {})})

        await asyncio.gather(*(per_date(i, c) for i, c in enumerate(contexts)), return_exceptions=True)


async def main() -> None:
    async with Actor:
        inp: dict = await Actor.get_input() or {}
        queries = [q.strip() for q in inp.get("searchQueries") or [] if isinstance(q, str) and q.strip()]
        hotels = [h.strip() for h in inp.get("hotels") or [] if isinstance(h, str) and h.strip()]
        if not queries and not hotels:
            await Actor.fail(status_message="Provide at least one search query (e.g. 'hotels in Istanbul') "
                                            "or one hotel (name, Google Hotels URL or hotel ID).")
            return

        today = datetime.now(timezone.utc).date()
        first = parse_date(inp.get("checkInDate"), today)
        if first < today:
            Actor.log.warning(f"checkInDate {first} is in the past, using today instead.")
            first = today
        nights = max(1, min(int(inp.get("nights") or 1), 30))
        n_dates = max(1, min(int(inp.get("numberOfDates") or 1), 365))
        step = max(1, min(int(inp.get("dateStep") or 1), 30))
        adults = max(1, min(int(inp.get("adults") or 2), 10))
        currency = (inp.get("currency") or "USD").upper()
        contexts = [SearchContext(first + timedelta(days=i * step), first + timedelta(days=i * step + nights),
                                  adults, currency) for i in range(n_dates)]

        proxy_cfg = await Actor.create_proxy_configuration(actor_proxy_input=inp.get("proxyConfiguration"))

        async def proxy_factory(session: str) -> str | None:
            return await proxy_cfg.new_url(session_id=session) if proxy_cfg else None

        client = GoogleHotelsClient(proxy_factory if proxy_cfg else None,
                                    hl=inp.get("language") or "en-US", gl=(inp.get("country") or "us").lower(),
                                    log=Actor.log, pool_size=max(4, int(inp.get("maxConcurrency", 5)) * 2))
        runner = Runner(inp, client)
        max_results = max(1, min(int(inp.get("maxHotelsPerSearch") or 20), 500))

        Actor.log.info(f"{len(queries)} search queries, {len(hotels)} hotels, {n_dates} check-in dates "
                       f"({contexts[0].check_in} .. {contexts[-1].check_in}), {nights} night(s), "
                       f"{adults} adults, {currency}, OTA offers: {runner.include_offers}")
        await Actor.set_status_message("Scraping Google Hotels...")

        tasks = [runner.run_search(q, c, max_results) for q in queries for c in contexts]
        tasks += [runner.run_hotel(h, contexts) for h in hotels]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception) and not isinstance(r, ChargeLimitReached):
                Actor.log.exception(r)

        await client.close()
        summary = {"itemsPushed": runner.pushed, "failed": len(runner.failed), "failures": runner.failed[:200],
                   "requests": client.stats}
        await Actor.set_value("RUN_SUMMARY", summary)
        msg = f"Done: {runner.pushed} hotel price rows"
        if runner.failed:
            msg += f", {len(runner.failed)} failed (see RUN_SUMMARY in key-value store)"
        Actor.log.info(f"{msg}. Requests: {client.stats}")
        await Actor.set_status_message(msg)
        if runner.pushed == 0 and runner.failed:
            await Actor.fail(status_message="No results. Google may be blocking requests; try residential proxies.")
