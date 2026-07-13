# Subito.it Property Scraper — Italy Real Estate Listings, Prices & Leads

[![Apify Actor](https://img.shields.io/badge/Apify-Actor-00A67E?logo=apify&logoColor=white)](https://apify.com/logiover/subito-it-property-scraper)
[![No API key](https://img.shields.io/badge/No%20API%20key-required-2ea44f)](https://apify.com/logiover/subito-it-property-scraper)
[![Pay per result](https://img.shields.io/badge/Pricing-Pay%20per%20result-1C7ED6)](https://apify.com/logiover/subito-it-property-scraper)
[![Export](https://img.shields.io/badge/Export-JSON%20%7C%20CSV%20%7C%20Excel-F59E0B)](https://apify.com/logiover/subito-it-property-scraper)

### ▶️ [Run Subito.it Property Scraper on Apify](https://apify.com/logiover/subito-it-property-scraper)

Scrape property listings from **Subito.it**, Italy's #1 classifieds portal — apartments, villas, land, garages, lofts, commercial space, rooms and vacation homes, for **sale, rent or vacation rent**. Target any **Italian region, province or city**, filter by **price (EUR), area, rooms and advertiser type**, and get **full address, GPS coordinates, computed €/m², advertiser details and listing badges** as clean structured JSON. **No login or API key required.**

Turn Italy's largest pool of property classifieds into an analysis-ready dataset — from Rome and Milan apartments to Tuscan villas and Sardinian holiday homes. Every record includes a computed **price per square meter** for instant €/m² comparison, plus **private-vs-agency** advertiser data for lead generation. Export thousands of Italian real-estate listings to CSV, Excel, JSON or your database. Ideal for **real-estate market research, investment screening, price tracking and B2B outreach**.

> **Why this Subito.it scraper?** 50+ fields per listing · sale / rent / vacation · hundreds–thousands of listings per run · computed €/m² · private-vs-agency advertiser leads · region → province → city targeting · export to JSON / CSV / Excel. The unofficial **Subito.it API alternative** for Italian real-estate data.

---

## 📊 What you get (output fields)

One row per listing, with pre-configured **Overview** and **Full Detail** views. Highlights:

| Field | Description |
|---|---|
| `adId` / `detailUrl` | Listing ID and full listing URL |
| `title` / `shortDescription` | Listing subject and body excerpt |
| `transactionType` / `propertyType` / `advertType` | sale/rent/vacation, property type, private/agency |
| `price` / `priceCurrency` / `pricePerSqm` | EUR price, currency, computed €/m² |
| `areaSqm` / `terrainAreaSqm` | Surface area and plot/terrain area |
| `rooms` / `roomsLabel` / `bathrooms` / `floor` / `totalFloors` | Room and floor details |
| `buildingType` / `heatingType` / `yearBuilt` / `energyClass` | Building features |
| `country` / `region` / `province` / `provinceCode` / `city` / `microLocation` / `street` / `fullAddress` | Full Italian address chain |
| `latitude` / `longitude` | GPS coordinates when present |
| `mainImageUrl` / `imageUrls` / `imageCount` | Main photo, all photo URLs, image count |
| `advertiserId` / `advertiserName` / `advertiserUrl` / `advertiserType` | Seller / advertiser info for lead gen |
| `hasElevator` / `hasParking` / `hasGarage` / `hasTerrace` / `hasBalcony` / `isFurnished` | Feature flags (detail-page fields, may be null) |
| `isFeatured` / `isUrgent` / `labels` | Vetrina / Urgente badges and raw labels |
| `datePosted` | Listing post date |
| `searchRegion` / `searchProvince` / `searchCity` / `searchKeyword` / `searchUrl` | Echo of search parameters |
| `scrapedAt` | ISO 8601 scrape timestamp |

---

## 💡 Use cases

- **Real-estate market research** — analyze €/m² pricing across Italian regions, provinces and cities.
- **Investment screening** — compare sale and rent listings to estimate yields and find undervalued properties.
- **Lead generation** — extract private sellers and agencies with advertiser details for B2B outreach.
- **Price & inventory tracking** — re-run on a schedule and diff datasets to monitor price changes and new listings.
- **Agency competitive intelligence** — filter by `advertiserType: agency` to map competitor inventory.
- **Vacation-rental analysis** — use `transaction: vacation` to study holiday-home supply and pricing (e.g. in Sardinia or Tuscany).
- **Valuation & relocation** — pull full address + GPS + area to feed maps, valuation models and CRMs.

---

## 🚀 Quick start

Four ways to run — all call the hosted Actor, nothing runs locally.

### 1) Apify Console (no code)

1. Open the Actor: **[apify.com/logiover/subito-it-property-scraper](https://apify.com/logiover/subito-it-property-scraper)**.
2. Click **Try for free**.
3. Pick a **region** (or `italia` for nationwide), optionally a province/city, choose a transaction and property type, then **Start**.
4. Open the **Output** tab (Overview or Full Detail view) and export to CSV, JSON or Excel.

### 2) Apify CLI

```bash
npm i -g apify-cli
apify login
apify call logiover/subito-it-property-scraper --input '{ "regionSlug": "lazio", "provinceSlug": "roma", "citySlug": "roma", "transaction": "sale", "propertyType": "apartment", "maxListings": 300 }'
```

### 3) REST API (curl)

```bash
curl -X POST \
  "https://api.apify.com/v2/acts/logiover~subito-it-property-scraper/run-sync-get-dataset-items?token=YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "regionSlug": "lombardia", "provinceSlug": "milano", "citySlug": "milano", "transaction": "rent", "maxListings": 300 }'
```

### 4) apify-client (JavaScript & Python)

```js
import { ApifyClient } from 'apify-client';
const client = new ApifyClient({ token: 'YOUR_API_TOKEN' });
const run = await client.actor('logiover/subito-it-property-scraper').call({
  regionSlug: 'lazio', provinceSlug: 'roma', citySlug: 'roma', transaction: 'sale', propertyType: 'apartment', maxListings: 300,
});
const { items } = await client.dataset(run.defaultDatasetId).listItems();
console.log(items);
```

```python
from apify_client import ApifyClient
client = ApifyClient("YOUR_API_TOKEN")
run = client.actor("logiover/subito-it-property-scraper").call(run_input={
    "regionSlug": "sardegna", "transaction": "vacation", "propertyType": "vacation_home", "maxListings": 300,
})
for p in client.dataset(run["defaultDatasetId"]).iterate_items():
    print(p.get("price"), p.get("pricePerSqm"), p.get("city"))
```

More detailed snippets: **[examples/cli.md](examples/cli.md)** · **[examples/api-curl.md](examples/api-curl.md)** · **[examples/javascript.md](examples/javascript.md)** · **[examples/python.md](examples/python.md)**

---

## ⚙️ Input

Pick a region (or `italia` for nationwide) and optionally drill down by province and city. Everything else is optional with sensible defaults.

| Field | Type | Default | Description |
|---|---|---|---|
| `regionSlug` | string (dropdown) | `italia` | Italian region slug (`italia` = nationwide). All 20 regions available |
| `provinceSlug` | string | `""` | Optional province slug after the region (e.g. `roma`, `milano`, `napoli`, `torino`) |
| `citySlug` | string | `""` | Optional city slug after the province. Requires `provinceSlug` |
| `transaction` | string (dropdown) | `sale` | `sale` (vendita), `rent` (affitto) or `vacation` (affitto-vacanze) |
| `propertyType` | string (dropdown) | `apartment` | apartment, villa, land, garage, loft, commercial, room (rent only), vacation_home (vacation only) |
| `keyword` | string | `""` | Optional free-text query |
| `priceMin` / `priceMax` | integer | `0` | Price range in EUR (`0` = no bound) |
| `areaMin` / `areaMax` | integer | `0` | Surface-area range in m² (`0` = no bound) |
| `roomsMin` / `roomsMax` | integer | `0` | Room-count (locali) range (`0` = no bound) |
| `advertiserType` | string (dropdown) | `all` | `all`, `private` or `agency` |
| `maxListings` | integer | `200` | Total cap on listings (`0` = unlimited) |
| `maxPagesPerTask` | integer | `10` | Pagination depth (~30 listings/page) |
| `requestDelay` | integer | `1500` | Delay between page requests (ms) |
| `maxRetries` | integer | `3` | Retries per request on errors |
| `proxyConfiguration` | object | Apify Proxy (IT) | Proxy configuration (a default is provided) |

> **Note:** `priceMin/Max`, `areaMin/Max`, `roomsMin/Max` and `advertiserType` are applied as post-fetch filters, so you always get accurate matches even where the site itself does not expose those as URL parameters. Rooms follow the Italian "locali" convention (a studio appears as `rooms: 1`).

**Example — apartments for sale in Rome:**

```json
{
  "regionSlug": "lazio",
  "provinceSlug": "roma",
  "citySlug": "roma",
  "transaction": "sale",
  "propertyType": "apartment",
  "priceMin": 150000,
  "priceMax": 400000,
  "areaMin": 60,
  "roomsMin": 2,
  "maxListings": 300
}
```

---

## 📤 Output

Results are stored in an Apify dataset (one row per listing) and can be exported to CSV, JSON, JSONL, Excel or XML, or pulled via the API.

**Sample item (trimmed):**

```json
{
  "adId": "512345678",
  "detailUrl": "https://www.subito.it/immobili/appartamento-roma-512345678.htm",
  "title": "Trilocale ristrutturato zona Prati",
  "shortDescription": "Appartamento luminoso di 85 m², 3 locali, 2° piano con ascensore...",
  "transactionType": "sale",
  "propertyType": "apartment",
  "advertType": "agency",
  "price": "320000",
  "priceCurrency": "EUR",
  "pricePerSqm": "3765",
  "areaSqm": "85",
  "rooms": "3",
  "bathrooms": "1",
  "floor": "2",
  "energyClass": "D",
  "country": "Italia",
  "region": "Lazio",
  "province": "Roma",
  "provinceCode": "RM",
  "city": "Roma",
  "microLocation": "Prati",
  "fullAddress": "Prati, Roma (RM)",
  "latitude": "41.9089",
  "longitude": "12.4610",
  "imageCount": "12",
  "advertiserId": "9981234",
  "advertiserName": "Immobiliare Roma Centro",
  "advertiserType": "agency",
  "isFeatured": "true",
  "isUrgent": "false",
  "datePosted": "2026-07-02",
  "searchRegion": "lazio",
  "scrapedAt": "2026-07-06T12:00:00.000Z"
}
```

> Note: GPS coordinates and feature flags like `hasElevator` come from per-listing detail data and may be `null` when a listing doesn't provide them (private listings often omit GPS).

---

## 🔗 Integrations & automation

- **Schedules** — monitor the Italian real-estate market daily or weekly.
- **Webhooks** — POST to your endpoint or Slack when a run finishes.
- **Google Sheets** — auto-sync results into a spreadsheet after each run.
- **Zapier / Make / n8n / Pipedream** — pipe listings into your CRM, valuation model, database or email reports.
- **Apify API** — start runs and pull datasets from your own backend.

---

## 📁 Export formats

CSV · JSON · JSONL · Excel (XLSX) · XML — one click in the Console, or add `&format=csv` to the API dataset URL.

---

## ❓ FAQ

### Does the Subito.it Property Scraper need an API key or login?
No. The Actor collects publicly visible Subito.it listing pages — no API key and no account are needed. You only need an Apify account to run it.

### Is this a Subito.it API alternative?
Yes. Subito.it offers no open public API for its Immobili listings, so this Actor works as an unofficial **Subito.it API alternative**, returning the same property data as structured rows ready to export.

### Can I scrape Subito.it without an API?
Yes. Just run the Actor with a region (and optionally province/city), transaction and property type. It returns clean, structured listing rows — no API key, no login.

### How do I scrape apartments for sale in Rome on Subito.it?
Set region `lazio` with province and city `roma`, transaction `sale` and propertyType `apartment`. The scraper exports listings with price and €/m² to CSV or JSON.

### Can I get the price per square meter for Subito.it listings?
Yes. Every record includes a computed `pricePerSqm` field, so you can analyze €/m² across Italian regions, provinces and cities after exporting to CSV or Excel.

### Can I filter by city, price and number of rooms?
Yes. Target any region, province or city slug, and filter by EUR price range, surface area, rooms (locali) and advertiser type.

### Why are some fields like latitude or hasElevator null?
Not all listings include GPS coordinates (private listings often skip them), and feature flags such as `hasElevator` and `hasParking` come from per-listing detail data — they are left null when unavailable.

### How much data can I get?
You can scrape hundreds to thousands of listings per run. For broad nationwide searches, the `maxListings` cap usually binds before the whole catalog is exhausted — narrow with price and area filters to slice large inventories.

### How do I generate leads (private sellers vs agencies)?
Set `advertiserType` to `private` for direct-seller leads or `agency` to map competitor inventory; each record carries `advertiserId`, `advertiserName` and `advertiserUrl`.

### How do I export Subito.it listings to CSV or Excel?
Open the run's **Output** tab and click **Export → CSV** or **XLSX**, or add `&format=csv` (or `xlsx`) to the API dataset URL.

---

## 🧩 Related actors by logiover

- **[Storia.ro Scraper](https://apify.com/logiover/storia-ro-scraper-romania-real-estate)** — Romanian real-estate listings with the same structured fields.
- **[Casa.it Scraper](https://apify.com/logiover/casa-it-scraper-italy-real-estate)** — another Italian property portal for cross-source coverage.

Browse the full European real-estate suite and 180+ actors: **[apify.com/logiover](https://apify.com/logiover)**.

---

📄 **Documentation only** — this repository contains no scraper source code. The Actor runs on the Apify platform. ▶️ **Run it:** [https://apify.com/logiover/subito-it-property-scraper](https://apify.com/logiover/subito-it-property-scraper)

Licensed under the [MIT License](LICENSE) · © 2026 logiover
