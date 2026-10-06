# Google Hotels Prices & OTA Rate Tracker

Get **hotel prices from Google Hotels** for any city, area or list of hotels: the lowest nightly rate, **every booking offer** (Booking.com, Expedia, Hotels.com, Agoda, Trip.com, Priceline, the hotel's official site and more), a **price calendar** across up to 365 check-in dates, Google's **typical price range**, tax breakdown and full hotel details.

Built for speed and reliability: no browser, no login, no cookies. A 25-hotel search with all OTA offers for 2 dates finishes in about 10 seconds.

## What can you do with it?

- **Hotel revenue management / rate shopping**: track your competitive set every day and see who undercuts you, on which channel, for which dates.
- **Rate parity monitoring**: compare your official-site price with every OTA for the same hotel and dates.
- **Price calendars**: scrape 30, 90 or 365 check-in dates in one run to find the cheapest nights, seasonality and events.
- **Travel agencies, tour operators, deal sites**: build hotel price feeds for any destination.
- **Market research**: average daily rate (ADR) by city, star class or neighborhood.
- **AI agents and automations**: clean JSON for n8n, Make, Zapier, Google Sheets or your LLM pipeline.

## Features

- Search by **query** (`hotels in Istanbul`, `hotels near Eiffel Tower`, `5 star hotels in Dubai Marina`) with automatic pagination.
- Track **specific hotels** by name, Google Hotels URL or hotel ID.
- **All OTA offers** per hotel and date: provider, nightly price, total price, booking link.
- **Price calendar**: many check-in dates per run, with a configurable step (every day, every week...).
- **Relative dates** (`+14 days`, `tomorrow`) so scheduled runs always look ahead.
- **Price insight**: Google's typical low/high range and whether today's price is `low`, `typical` or `high`.
- **Stay total** with base price and taxes & fees.
- Optional **room types** with room-level prices.
- 30+ currencies, any country as point of sale, any language.
- Pay only for results.

## Input example

Track a competitive set for the next 30 nights:

```json
{
  "hotels": [
    "Hilton Istanbul Bomonti",
    "The Marmara Taksim",
    "https://www.google.com/travel/hotels/entity/ChkIwcfg4NGyvbu8ARoML2cvMWhjMl9xbDg5EAE"
  ],
  "checkInDate": "+1 day",
  "numberOfDates": 30,
  "nights": 1,
  "adults": 2,
  "currency": "EUR",
  "includeOtaOffers": true
}
```

Scrape a whole destination:

```json
{
  "searchQueries": ["hotels in Barcelona"],
  "maxHotelsPerSearch": 200,
  "checkInDate": "2026-12-20",
  "nights": 3,
  "currency": "USD"
}
```

## Output example

One row per hotel per check-in date:

```json
{
  "hotelName": "Résidence Hoche",
  "hotelId": "ChoIv9zm0pCp0vObARoNL2cvMTFkZHd0ZzdmeBAB",
  "checkIn": "2026-11-05",
  "checkOut": "2026-11-07",
  "nights": 2,
  "adults": 2,
  "currency": "EUR",
  "lowestPricePerNight": 87.26,
  "lowestTotalPrice": 174.52,
  "lowestPriceProvider": "Super.com",
  "offersCount": 14,
  "offers": [
    { "provider": "Super.com", "pricePerNight": 87.26, "totalPrice": 174.52, "bookingUrl": "https://www.google.com/travel/lodging/clk?..." },
    { "provider": "Agoda", "pricePerNight": 97.58, "totalPrice": 195.16, "bookingUrl": "https://www.google.com/travel/lodging/clk?..." },
    { "provider": "Hotels.com", "pricePerNight": 99.0, "totalPrice": 198.0, "bookingUrl": "https://www.google.com/travel/lodging/clk?..." }
  ],
  "priceInsight": { "currentPrice": 95, "typicalLowPrice": 78, "typicalHighPrice": 105, "priceLevel": "typical" },
  "stayTotal": { "baseTotal": 156.94, "taxesAndFees": 15.7, "grandTotal": 174.52 },
  "rating": 3.8,
  "reviewCount": 106,
  "hotelClass": null,
  "address": "49 Rue Charles Nodier, 93310 Le Pré-Saint-Gervais, France",
  "phone": "+33 1 48 45 40 10",
  "website": "http://residence-hoche.com.es/",
  "latitude": 48.889185,
  "longitude": 2.4014425,
  "countryCode": "FR",
  "googleHotelsUrl": "https://www.google.com/travel/search?q=...",
  "scrapedAt": "2026-10-06T18:14:29+00:00"
}
```

The dataset has two ready-made views: **Prices overview** (one line per hotel and date) and **All OTA offers** (one line per provider offer), both exportable to CSV, Excel or JSON.

## Pricing

You pay per result row (one hotel for one check-in date):

| Mode | What you get |
|---|---|
| **With OTA offers** (default) | Every booking offer, price insight, tax breakdown, hotel details |
| **Listing only** (`includeOtaOffers: false`) | Lowest price and hotel details from the search results, cheaper and faster |

Platform usage is included in the price. Set **Max results** or a maximum cost per run to stay on budget.

## Tips

- **Scheduled monitoring**: create a task with relative dates (`checkInDate: "+1 day"`, `numberOfDates: 30`) and schedule it daily. Combine with a webhook or the Google Sheets integration for alerts.
- **Point of sale matters**: prices and the list of booking sites differ by country. Set `country` to your customers' market.
- **Hotel names**: add the city for an exact match (`Hilton Bomonti Istanbul`). The matched hotel is returned in `hotelName` and `hotelId`; reuse the ID for future runs.
- If you see many failed requests in the log, switch the proxy to residential.

## FAQ

**Which booking sites are included?**
Whatever Google Hotels shows for that hotel, market and date: typically Booking.com, Expedia, Hotels.com, Agoda, Trip.com, Priceline, Vio.com, Trivago deals, the official hotel website and many regional sites.

**Are prices per night or total?**
Both. `pricePerNight` and `totalPrice` (for the whole stay) are returned for every offer, plus `stayTotal` with taxes and fees.

**Can I get more than 20 hotels per city?**
Yes. Set `maxHotelsPerSearch` (up to 500); the Actor paginates automatically.

**Is it legal?**
The Actor only collects publicly available pricing information shown on Google Hotels, without logging in. You are responsible for using the data in line with applicable laws and the terms of the sources.

## Support

Found a bug or need a field that is not there yet? Open an issue on the Issues tab. Issues are typically answered within 24 hours.
