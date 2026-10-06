# Google Hotels Prices & OTA Rate Tracker

[![Run on Apify](https://apify.com/actor-badge?actor=kamerozkan/google-hotels-prices)](https://apify.com/kamerozkan/google-hotels-prices)
[![Pricing](https://img.shields.io/badge/Pricing-Pay--Per--Event%20($0.003)-blue)](https://apify.com/kamerozkan/google-hotels-prices)
[![Memory](https://img.shields.io/badge/Memory-512%20MB-green)](https://apify.com/kamerozkan/google-hotels-prices)
[![Status](https://img.shields.io/badge/Engine-Direct%20RPC%20(No%20Browser)-success)](https://apify.com/kamerozkan/google-hotels-prices)

Extract real-time **hotel prices, rate parity insights, and OTA booking offers** from Google Hotels for any city, landmark, or list of properties. Retrieve the lowest nightly rate, all booking site offers (Booking.com, Expedia, Hotels.com, Agoda, Trip.com, Priceline, official hotel sites), multi-date price calendars (up to 365 days), Google's typical price benchmark, tax breakdowns, and full property metadata.

Built for speed and reliability: **browserless direct protocol engine**, no login, no cookies, no heavy headless browser overhead.

---

## Why Google Hotels Scraper?

| Feature | This Actor (kamerozkan) | SerpApi / Traditional APIs | Playwright / Puppeteer Scrapers |
| :--- | :--- | :--- | :--- |
| **Pricing Model** | **$0.003 / hotel with all OTAs** | $0.015 - $0.020 / call | $50 - $150 / mo + heavy compute |
| **Execution Speed** | **2 - 4 seconds** | 8 - 15 seconds | 35 - 60 seconds |
| **Memory Footprint** | **512 MB** | N/A (External cloud) | 2048 MB - 4096 MB |
| **All OTA Offers** | **Yes (10+ booking channels)** | Single price or extra fee | Requires clicking into modal |
| **Price Benchmark** | **Yes (`low`, `typical`, `high`)** | Rarely supported | No |
| **Multi-Date Calendars** | **Yes (up to 365 check-in dates)**| Separate calls billed | Multiplies run time by 10x |

---

## Core Use Cases

- **Hotel Revenue Management & Rate Shopping:** Track your hotel's competitive set daily. See which OTA undercuts your official rate and monitor price shifts in real time.
- **Rate Parity Enforcement:** Verify whether Booking.com, Expedia, or Agoda are violating parity agreements for your rooms across upcoming seasons.
- **Price Calendars & Seasonality Analysis:** Scan 30, 90, or 365 check-in dates in a single run to uncover peak demand dates, holiday surges, and low-season troughs.
- **Travel Tech & Deal Sites:** Build high-frequency hotel price comparison engines and deal alert feeds for any city worldwide.
- **AI Agents & Workflows:** Integrate clean JSON directly into n8n, Make, Zapier, LangChain, or LLM-driven travel planners.

---

## Key Features

- **Query-Based Discovery:** Search any destination (`hotels in Paris`, `luxury hotels in Manhattan`, `cheap hotels near Colosseum`) with automatic pagination.
- **Specific Hotel Monitoring:** Track designated hotels by name, Google Hotels entity URL, or `hotelId`.
- **All OTA Offers in One Row:** Receive provider name, nightly price, stay total, and direct booking URL for every booking channel.
- **Google Price Insight:** Instant comparison against historical averages (`priceLevel`: `low`, `typical`, `high`) with low/high threshold values.
- **Stay Total & Tax Breakdown:** Base room total plus estimated taxes and fees.
- **Relative Dates:** Use dynamic expressions (`+14 days`, `tomorrow`) for automated daily monitoring without updating dates manually.
- **30+ Currencies & Global Point of Sale:** Set currency (USD, EUR, GBP, TRY) and country market code (US, GB, DE, TR).

---

## Input Parameters

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `searchQueries` | Array of Strings | No | `["hotels in Paris"]` | Search destinations or landmarks to discover hotels. |
| `hotels` | Array of Strings | No | `[]` | Specific hotel names or Google Hotels URLs to track. |
| `checkInDate` | String | No | `"today+14"` | Check-in date (`YYYY-MM-DD` or relative like `+14 days`, `tomorrow`). |
| `numberOfDates` | Integer | No | `1` | Scan multiple consecutive check-in dates (1 to 365). |
| `dateStep` | Integer | No | `1` | Step in days between calendar dates (e.g. 7 for weekly). |
| `nights` | Integer | No | `1` | Length of stay in nights (1 to 30). |
| `adults` | Integer | No | `2` | Number of adult guests (1 to 6). |
| `currency` | String | No | `"USD"` | 3-letter currency code (USD, EUR, GBP, TRY, etc.). |
| `includeOtaOffers`| Boolean | No | `true` | Extract all OTA booking site offers. If false, extracts lowest price only. |
| `maxHotelsPerSearch` | Integer | No | `20` | Maximum properties to collect per search query (up to 500). |
| `proxyConfiguration` | Object | No | `{ "useApifyProxy": true }` | Apify proxy settings (Datacenter or Residential). |

---

## Example JSON Output

Each record represents one hotel property for a specific check-in date:

```json
{
  "hotelName": "The Marmara Taksim",
  "hotelId": "ChoIv9zm0pCp0vObARoNL2cvMTFkZHd0ZzdmeBAB",
  "checkIn": "2026-11-05",
  "checkOut": "2026-11-07",
  "nights": 2,
  "adults": 2,
  "currency": "EUR",
  "lowestPricePerNight": 145.0,
  "lowestTotalPrice": 290.0,
  "lowestPriceProvider": "Booking.com",
  "offersCount": 8,
  "offers": [
    {
      "provider": "Booking.com",
      "pricePerNight": 145.0,
      "totalPrice": 290.0,
      "bookingUrl": "https://www.google.com/travel/lodging/clk?..."
    },
    {
      "provider": "Official Site",
      "pricePerNight": 150.0,
      "totalPrice": 300.0,
      "bookingUrl": "https://www.google.com/travel/lodging/clk?..."
    },
    {
      "provider": "Expedia",
      "pricePerNight": 152.0,
      "totalPrice": 304.0,
      "bookingUrl": "https://www.google.com/travel/lodging/clk?..."
    }
  ],
  "priceInsight": {
    "currentPrice": 145,
    "typicalLowPrice": 130,
    "typicalHighPrice": 180,
    "priceLevel": "typical"
  },
  "stayTotal": {
    "baseTotal": 260.0,
    "taxesAndFees": 30.0,
    "grandTotal": 290.0
  },
  "rating": 4.5,
  "reviewCount": 4210,
  "address": "Taksim Meydani, Istanbul, Turkey",
  "latitude": 41.0369,
  "longitude": 28.9850,
  "googleHotelsUrl": "https://www.google.com/travel/search?q=...",
  "scrapedAt": "2026-10-06T20:30:00+00:00"
}
```

---

## Code Examples

### Python (apify-client)

```python
from apify_client import ApifyClient

client = ApifyClient("YOUR_APIFY_API_TOKEN")

run_input = {
    "searchQueries": ["hotels in Istanbul"],
    "checkInDate": "+14 days",
    "nights": 2,
    "adults": 2,
    "currency": "USD",
    "includeOtaOffers": True,
    "maxHotelsPerSearch": 25,
}

# Run the Actor and wait for it to finish
run = client.actor("kamerozkan/google-hotels-prices").call(run_input=run_input)

# Fetch results from default dataset
for item in client.dataset(run["defaultDatasetId"]).iterate_items():
    print(f"{item['hotelName']}: lowest ${item['lowestPricePerNight']} on {item['lowestPriceProvider']}")
```

### JavaScript / Node.js (apify-client)

```javascript
import { ApifyClient } from 'apify-client';

const client = new ApifyClient({
    token: 'YOUR_APIFY_API_TOKEN',
});

const runInput = {
    searchQueries: ['hotels in Barcelona'],
    checkInDate: '+7 days',
    nights: 1,
    currency: 'EUR',
    includeOtaOffers: true,
};

const run = await client.actor('kamerozkan/google-hotels-prices').call(runInput);
const { items } = await client.dataset(run.defaultDatasetId).listItems();

console.log(`Extracted ${items.length} hotel rate records:`, items);
```

### cURL

```bash
curl --request POST \
  --url "https://api.apify.com/v2/acts/kamerozkan~google-hotels-prices/runs?token=YOUR_APIFY_API_TOKEN" \
  --header "Content-Type: application/json" \
  --data '{
    "searchQueries": ["hotels in Rome"],
    "checkInDate": "2026-12-01",
    "nights": 2,
    "currency": "EUR"
  }'
```

---

## Pricing Details

This Actor operates under **Pay-Per-Event (PPE)**:
- **Full Hotel Offer ($0.003):** Charged per hotel per check-in date with complete OTA rates, price insights, and stay total.
- **Listing Only ($0.001):** Charged per hotel when `includeOtaOffers: false` (fastest search mode).

Platform compute usage is fully included in the event price. You can set a spending limit in Apify Console to prevent overruns.
