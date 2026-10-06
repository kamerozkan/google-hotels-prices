"""Google Hotels client built on Google Travel's internal batchexecute RPCs.

RPCs used:
    AtySUc  hotel search (list) and single-hotel lookup by entity id
    M0CRd   all booking offers (OTAs + official site) for one hotel and date range

Responses are positional JSON (protobuf-like arrays). Every accessor goes through
`_g()` so that a missing field yields None instead of crashing the run.
"""

from __future__ import annotations

import asyncio
import base64
import json
import random
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs, quote, urlencode, urlparse

import httpx

ENDPOINT = "https://www.google.com/_/TravelFrontendUi/data/batchexecute"
GOOGLE = "https://www.google.com"
HOTEL_NODE_KEYS = ("397419284", "441552390")

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
]

ENTITY_RE = re.compile(r"^Ch[A-Za-z0-9_\-]{20,80}$")


class BlockedError(Exception):
    """Google returned something that is not a valid RPC payload (rate limit, captcha, consent)."""


# --------------------------------------------------------------------------- helpers


def _g(obj: Any, *path: Any) -> Any:
    """Safe nested getter for positional JSON."""
    for p in path:
        try:
            obj = obj[p]
        except (IndexError, KeyError, TypeError):
            return None
    return obj


def _ymd(d: date) -> list[int]:
    return [d.year, d.month, d.day]


def _money(node: Any) -> tuple[float | None, str | None]:
    """Price node looks like ["$95", null, 94.98, null, 95] -> (94.98, "$95")."""
    if not isinstance(node, list):
        return None, None
    text = _g(node, 0) if isinstance(_g(node, 0), str) else None
    exact = _g(node, 2)
    if not isinstance(exact, (int, float)):
        exact = _g(node, 4) if isinstance(_g(node, 4), (int, float)) else None
    return (round(float(exact), 2) if exact is not None else None), text


def _parse_money_text(text: Any) -> float | None:
    if not isinstance(text, str):
        return None
    digits = re.sub(r"[^\d.,]", "", text).strip(".,")
    if not digits:
        return None
    # A trailing separator followed by exactly 1-2 digits is a decimal mark; every other separator groups thousands.
    m = re.fullmatch(r"(.*?)[.,](\d{1,2})", digits)
    if m and re.search(r"\d", m.group(1) or ""):
        whole, frac = re.sub(r"[.,]", "", m.group(1)), m.group(2)
    else:
        whole, frac = re.sub(r"[.,]", "", digits), "0"
    try:
        return float(f"{whole}.{frac}")
    except ValueError:
        return None


def _abs_url(u: Any) -> str | None:
    if not isinstance(u, str) or not u:
        return None
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return GOOGLE + u
    return u


def entity_to_qs(entity: str) -> str:
    raw = b"\x32" + bytes([len(entity)]) + entity.encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def hotel_url(entity: str, check_in: date | None = None, check_out: date | None = None,
              hl: str = "en-US", gl: str = "us", name: str | None = None) -> str:
    q = name or "hotel"
    if check_in and check_out:
        q += f" {check_in.strftime('%b %d %Y')} to {check_out.strftime('%b %d %Y')}"
    return f"{GOOGLE}/travel/search?" + urlencode({"q": q, "qs": entity_to_qs(entity), "hl": hl, "gl": gl})


def extract_entity(value: str) -> str | None:
    """Accepts a raw entity id, a /travel/hotels/entity/<id> URL or a /travel/search?...&qs=<b64> URL."""
    value = value.strip()
    if ENTITY_RE.match(value):
        return value
    if "google." not in value:
        return None
    m = re.search(r"/entity/([A-Za-z0-9_\-]+)", value)
    if m and ENTITY_RE.match(m.group(1)):
        return m.group(1)
    qs = parse_qs(urlparse(value).query).get("qs", [None])[0]
    if qs:
        try:
            raw = base64.urlsafe_b64decode(qs + "=" * (-len(qs) % 4))
            # field 6 (0x32), length-delimited: 0x32 <len> <entity bytes> ...
            if len(raw) > 2 and raw[0] == 0x32:
                cand = raw[2:2 + raw[1]].decode("ascii", "ignore")
                if ENTITY_RE.match(cand):
                    return cand
            m = re.search(rb"Ch[A-Za-z0-9_\-]{20,80}", raw)
            if m:
                return m.group(0).decode()
        except Exception:  # noqa: BLE001
            return None
    return None


# --------------------------------------------------------------------------- parsers


def parse_hotel_node(e: list) -> dict:
    """Parses a hotel node shared by search results and single-hotel lookups."""
    info = _g(e, 2) or []
    out: dict[str, Any] = {
        "hotelName": _g(e, 1),
        "hotelId": _g(e, 20),
        "googleMapsId": _g(e, 9) if isinstance(_g(e, 9), str) else None,
        "hotelClass": _g(e, 3, 1) if isinstance(_g(e, 3, 1), int) else None,
        "hotelType": _g(e, 3, 0),
        "rating": _g(e, 7, 0, 0),
        "reviewCount": _g(e, 7, 0, 1),
        "description": _g(e, 11, 0),
        "thumbnailUrl": _g(e, 12, 0),
        "latitude": _g(info, 0, 0),
        "longitude": _g(info, 0, 1),
        "address": None,
        "phone": None,
        "website": None,
        "checkInTime": None,
        "checkOutTime": None,
        "countryCode": None,
    }
    # Field positions inside `info` shift between search and detail responses,
    # so detect them by shape instead of index.
    for item in info if isinstance(info, list) else []:
        if out["address"] is None and isinstance(_g(item, 0, 0, 0), str) and len(item) == 1:
            out["address"] = _g(item, 0, 0, 0)
        elif out["phone"] is None and isinstance(item, list) and len(item) == 2 and \
                isinstance(item[1], str) and item[1].startswith("tel:"):
            out["phone"] = item[0]
        elif out["website"] is None and isinstance(_g(item, 2), str) and item[2].startswith("http") \
                and "google." not in item[2] and _g(item, 0) is None:
            out["website"] = item[2]
        elif out["checkInTime"] is None and isinstance(item, list) and len(item) == 2 and \
                all(isinstance(x, str) and re.search(r"\d{1,2}[:.]\d{2}", x) for x in item):
            out["checkInTime"], out["checkOutTime"] = item
        elif isinstance(item, str) and re.fullmatch(r"[A-Z]{2}", item):
            out["countryCode"] = item
    price, price_text = _money(_g(e, 6, 2, 1))
    out["lowestPricePerNight"] = price
    out["lowestPricePerNightText"] = price_text
    return out


def find_hotel_nodes(payload: Any) -> list[list]:
    """Walks the response and returns every hotel node (search list or detail)."""
    found: list[list] = []
    seen: set[str] = set()

    def walk(x: Any, depth: int = 0) -> None:
        if depth > 12:
            return
        if isinstance(x, dict):
            for k, v in x.items():
                if k in HOTEL_NODE_KEYS:
                    node = v[0] if isinstance(v, list) and v and isinstance(v[0], list) and isinstance(_g(v, 0, 1), str) else v
                    if isinstance(node, list) and isinstance(_g(node, 1), str) and isinstance(_g(node, 20), str):
                        if node[20] not in seen:
                            seen.add(node[20])
                            found.append(node)
                        continue
                walk(v, depth + 1)
        elif isinstance(x, list):
            for v in x:
                walk(v, depth + 1)

    walk(payload)
    return found


def parse_next_page_token(payload: Any) -> str | None:
    """Search responses carry a {"410579159": [token, "", 15000, page, pageSize]} block."""
    token = None

    def walk(x: Any, depth: int = 0) -> None:
        nonlocal token
        if token or depth > 8:
            return
        if isinstance(x, dict):
            if "410579159" in x and isinstance(_g(x, "410579159", 0), str):
                token = x["410579159"][0] or None
                return
            for v in x.values():
                walk(v, depth + 1)
        elif isinstance(x, list):
            for v in x:
                walk(v, depth + 1)

    walk(payload)
    return token


def parse_offers(payload: Any, include_rooms: bool) -> dict:
    """Parses the M0CRd response: lowest price, all offers, price insight, optional room types."""
    r2 = _g(payload, 2)
    if not isinstance(r2, list):
        return {"offers": [], "lowestPricePerNight": None}
    lowest, lowest_text = _money(_g(r2, 1))
    offers = []
    for o in _g(r2, 21) or []:
        nightly, nightly_text = _money(_g(o, 12, 4))
        total, total_text = _money(_g(o, 12, 5))
        offers.append({
            "provider": _g(o, 0, 0),
            "pricePerNight": nightly,
            "pricePerNightText": nightly_text,
            "totalPrice": total,
            "totalPriceText": total_text,
            "bookingUrl": _abs_url(_g(o, 0, 2)),
            "providerLogo": _abs_url(_g(o, 0, 3, 0)),
        })
    offers = [o for o in offers if o["provider"]]
    offers.sort(key=lambda o: (o["pricePerNight"] is None, o["pricePerNight"] or 0))

    insight_node = _g(r2, 7, 1, 0, 16)
    insight = None
    if isinstance(insight_node, list) and len(insight_node) >= 3:
        insight = {
            "currentPrice": _parse_money_text(insight_node[0]),
            "typicalLowPrice": _parse_money_text(insight_node[1]),
            "typicalHighPrice": _parse_money_text(insight_node[2]),
        }
        cur, lo, hi = insight["currentPrice"], insight["typicalLowPrice"], insight["typicalHighPrice"]
        if None not in (cur, lo, hi):
            insight["priceLevel"] = "low" if cur < lo else "high" if cur > hi else "typical"

    breakdown = _g(r2, 44)
    stay = None
    if isinstance(breakdown, list) and len(breakdown) >= 4 and all(isinstance(x, (int, float)) for x in breakdown[:4]):
        stay = {"baseTotal": round(breakdown[0], 2), "taxesAndFees": round(breakdown[1], 2),
                "grandTotal": round(breakdown[3], 2)}

    out = {
        "lowestPricePerNight": lowest if lowest is not None else (offers[0]["pricePerNight"] if offers else None),
        "lowestPricePerNightText": lowest_text,
        "lowestPriceProvider": offers[0]["provider"] if offers else None,
        "offersCount": len(offers),
        "offers": offers,
        "priceInsight": insight,
        "stayTotal": stay,
    }

    if include_rooms:
        rooms = []
        for prov in _g(r2, 2) or []:
            pname = _g(prov, 0, 0)
            for room in _g(prov, 7) or []:
                rates = []
                for rate in _g(room, 2) or []:
                    n, _ = _money(_g(rate, 4))
                    t, _ = _money(_g(rate, 5))
                    rates.append({"pricePerNight": n, "totalPrice": t, "bookingUrl": _abs_url(_g(rate, 0)),
                                  "maxGuests": _g(rate, 1, 0)})
                rates = [x for x in rates if x["pricePerNight"] is not None]
                if not rates:
                    continue
                rates.sort(key=lambda x: x["pricePerNight"])
                rooms.append({"provider": pname, "roomName": _g(room, 0),
                              "lowestPricePerNight": rates[0]["pricePerNight"],
                              "lowestTotalPrice": rates[0]["totalPrice"],
                              "ratesCount": len(rates), "rates": rates})
        out["roomTypes"] = rooms
    return out


# --------------------------------------------------------------------------- client


@dataclass
class SearchContext:
    check_in: date
    check_out: date
    adults: int
    currency: str


class GoogleHotelsClient:
    def __init__(self, proxy_url_factory: Callable[[str], Awaitable[str | None]] | None,
                 hl: str = "en-US", gl: str = "us", max_retries: int = 6, log: Any = None,
                 pool_size: int = 8) -> None:
        self._proxy_url_factory = proxy_url_factory
        self.hl = hl
        self.gl = gl
        self.max_retries = max_retries
        self.log = log
        self.pool_size = pool_size
        self._pool: list[str] = []
        self._clients: dict[str, httpx.AsyncClient] = {}
        self.stats = {"requests": 0, "retries": 0, "blocked": 0}

    async def close(self) -> None:
        await asyncio.gather(*(c.aclose() for c in self._clients.values()), return_exceptions=True)

    async def _client(self, session: str) -> httpx.AsyncClient:
        if session not in self._clients:
            proxy = await self._proxy_url_factory(session) if self._proxy_url_factory else None
            self._clients[session] = httpx.AsyncClient(proxy=proxy, timeout=httpx.Timeout(40.0), http2=True,
                                                       follow_redirects=False)
        return self._clients[session]

    async def _drop(self, session: str) -> None:
        c = self._clients.pop(session, None)
        if c:
            await c.aclose()

    def _pick_session(self) -> str:
        while len(self._pool) < self.pool_size:
            self._pool.append(f"s{random.randint(1, 10**9)}")
        return random.choice(self._pool)

    async def _retire(self, session: str) -> None:
        if session in self._pool:
            self._pool.remove(session)
        await self._drop(session)

    async def rpc(self, rpcid: str, payload: list) -> Any:
        """Returns the decoded RPC payload, or None when Google answered but had no data."""
        freq = json.dumps([[[rpcid, json.dumps(payload, separators=(",", ":")), None, "generic"]]],
                          separators=(",", ":"))
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            session = self._pick_session()
            params = {"rpcids": rpcid, "source-path": "/travel/search", "hl": self.hl, "gl": self.gl,
                      "soc-app": "162", "soc-platform": "1", "soc-device": "1",
                      "_reqid": str(random.randint(10000, 999999)), "rt": "c"}
            headers = {"User-Agent": random.choice(USER_AGENTS),
                       "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                       "Accept-Language": f"{self.hl},en;q=0.8", "Accept-Encoding": "gzip, deflate",
                       "Origin": GOOGLE, "Referer": f"{GOOGLE}/travel/search", "X-Same-Domain": "1"}
            try:
                self.stats["requests"] += 1
                client = await self._client(session)
                resp = await client.post(f"{ENDPOINT}?{urlencode(params)}", data={"f.req": freq}, headers=headers)
                if resp.status_code != 200:
                    raise BlockedError(f"HTTP {resp.status_code}")
                found, data = self._decode(resp.text, rpcid)
                if not found:
                    raise BlockedError("no RPC envelope in response")
                return data
            except (BlockedError, httpx.HTTPError) as err:
                last_err = err
                self.stats["retries"] += 1
                if isinstance(err, BlockedError):
                    self.stats["blocked"] += 1
                await self._retire(session)
                if self.log and attempt >= 2:
                    self.log.debug(f"{rpcid} attempt {attempt + 1} failed: {err}")
                await asyncio.sleep(min(2 ** attempt, 20) * random.uniform(0.5, 1.0))
        raise RuntimeError(f"{rpcid} failed after {self.max_retries} attempts: {last_err}")

    @staticmethod
    def _decode(text: str, rpcid: str) -> tuple[bool, Any]:
        """(envelope_found, payload). payload is None when Google returned an empty result."""
        found = False
        for line in text.split("\n"):
            line = line.strip()
            if not line.startswith("[["):
                continue
            try:
                items = json.loads(line)
            except json.JSONDecodeError:
                continue
            for item in items:
                if _g(item, 0) == "wrb.fr" and _g(item, 1) == rpcid:
                    found = True
                    if isinstance(_g(item, 2), str):
                        return True, json.loads(item[2])
        return found, None

    # -- high level calls ----------------------------------------------------

    @staticmethod
    def _dates_block(ctx: SearchContext) -> list:
        return [1, None, [None, [None, [_ymd(ctx.check_in), _ymd(ctx.check_out), ctx.adults], None, None, None, [1]]],
                None, [[None] * 6 + [ctx.currency]]]

    async def search(self, query: str, ctx: SearchContext, max_results: int) -> list[dict]:
        hotels: list[dict] = []
        seen: set[str] = set()
        token: str | None = None
        for _ in range(50):
            tail: list = [1, token, None, None, None, None, 13]
            payload: list = [query, self._dates_block(ctx), tail]
            data = await self.rpc("AtySUc", payload)
            new = 0
            for node in find_hotel_nodes(data):
                h = parse_hotel_node(node)
                if h["hotelId"] and h["hotelId"] not in seen:
                    seen.add(h["hotelId"])
                    hotels.append(h)
                    new += 1
                    if len(hotels) >= max_results:
                        return hotels
            token = parse_next_page_token(data)
            if not token or new == 0:
                break
        return hotels

    async def lookup(self, entity: str, ctx: SearchContext) -> dict | None:
        payload = ["", self._dates_block(ctx), [None, None, None, None, None, entity, 13], None, 1]
        data = await self.rpc("AtySUc", payload)
        for node in find_hotel_nodes(data):
            if _g(node, 20) == entity:
                return parse_hotel_node(node)
        return None

    async def offers(self, entity: str, ctx: SearchContext, include_rooms: bool) -> dict:
        payload = [None, [None, None, None, ctx.currency, [_ymd(ctx.check_in), _ymd(ctx.check_out), ctx.adults, 1]],
                   [1, None, 1], entity, [None, None, None, None, None, None, 1, None, 2], 1, 2]
        data = await self.rpc("M0CRd", payload)
        return parse_offers(data, include_rooms)


def build_hotel_url(entity: str, name: str | None, ctx: SearchContext, hl: str, gl: str) -> str:
    return hotel_url(entity, ctx.check_in, ctx.check_out, hl=hl, gl=gl, name=name)


def google_query_url(query: str, ctx: SearchContext, hl: str, gl: str) -> str:
    q = f"{query} {ctx.check_in.strftime('%b %d %Y')} to {ctx.check_out.strftime('%b %d %Y')}"
    return f"{GOOGLE}/travel/search?q={quote(q)}&hl={hl}&gl={gl}"
