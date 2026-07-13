# Subito.it Property Scraper — REST API (curl) examples

Call the [Subito.it Property Scraper](https://apify.com/logiover/subito-it-property-scraper) over the Apify REST API. Replace `YOUR_API_TOKEN` with your token from [Apify Console → Integrations](https://console.apify.com/account/integrations).

The Actor id in the API is `logiover~subito-it-property-scraper`.

## Run and get results in one call (synchronous)

```bash
curl -X POST \
  "https://api.apify.com/v2/acts/logiover~subito-it-property-scraper/run-sync-get-dataset-items?token=YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "regionSlug": "lazio",
    "provinceSlug": "roma",
    "citySlug": "roma",
    "transaction": "sale",
    "propertyType": "apartment",
    "maxListings": 300
  }'
```

## Get CSV output

```bash
curl -X POST \
  "https://api.apify.com/v2/acts/logiover~subito-it-property-scraper/run-sync-get-dataset-items?token=YOUR_API_TOKEN&format=csv" \
  -H "Content-Type: application/json" \
  -d '{ "regionSlug": "lombardia", "provinceSlug": "milano", "citySlug": "milano", "transaction": "rent", "maxListings": 500 }' \
  -o subito-milan-rent.csv
```

## Private-seller listings (lead generation)

```bash
curl -X POST \
  "https://api.apify.com/v2/acts/logiover~subito-it-property-scraper/run-sync-get-dataset-items?token=YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "regionSlug": "campania",
    "provinceSlug": "napoli",
    "transaction": "sale",
    "advertiserType": "private",
    "maxListings": 500
  }'
```

## Start a run asynchronously, then fetch the dataset

```bash
# 1) Start the run
curl -X POST \
  "https://api.apify.com/v2/acts/logiover~subito-it-property-scraper/runs?token=YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "regionSlug": "sardegna", "transaction": "vacation", "propertyType": "vacation_home", "maxListings": 1000 }'
# -> note "id" and "defaultDatasetId"
```

```bash
# 2) Poll run status
curl "https://api.apify.com/v2/actor-runs/RUN_ID?token=YOUR_API_TOKEN"
```

```bash
# 3) Download items when SUCCEEDED
curl "https://api.apify.com/v2/datasets/DATASET_ID/items?token=YOUR_API_TOKEN&format=json" \
  -o subito-vacation.json
```

## Handy query parameters

- `format=csv|json|jsonl|xlsx|xml`
- `clean=true` — omit empty/internal fields.
- `fields=adId,price,pricePerSqm,city,province,detailUrl` — return only selected columns.
- `view=detail` — request the full-detail dataset view (all 50+ fields).
- `limit` / `offset` — page through large datasets.

> Prefer sending the token in an `Authorization: Bearer YOUR_API_TOKEN` header rather than the query string.
