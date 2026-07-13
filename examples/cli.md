# Subito.it Property Scraper — Apify CLI examples

Run the [Subito.it Property Scraper](https://apify.com/logiover/subito-it-property-scraper) from your terminal with the Apify CLI. These snippets only *call* the hosted Actor.

## Install & log in

```bash
npm install -g apify-cli
apify login   # paste your Apify API token
```

## Apartments for sale in Rome (filtered)

```bash
apify call logiover/subito-it-property-scraper --input '{
  "regionSlug": "lazio",
  "provinceSlug": "roma",
  "citySlug": "roma",
  "transaction": "sale",
  "propertyType": "apartment",
  "priceMin": 150000,
  "priceMax": 400000,
  "maxListings": 300
}'
```

## Private-seller rentals in Milan (lead generation)

```bash
apify call logiover/subito-it-property-scraper --input '{
  "regionSlug": "lombardia",
  "provinceSlug": "milano",
  "citySlug": "milano",
  "transaction": "rent",
  "propertyType": "apartment",
  "advertiserType": "private",
  "maxListings": 500
}'
```

## Vacation homes in Sardinia

```bash
apify call logiover/subito-it-property-scraper --input '{
  "regionSlug": "sardegna",
  "transaction": "vacation",
  "propertyType": "vacation_home",
  "maxListings": 300
}'
```

## Use an input file

Create `input.json`:

```json
{
  "regionSlug": "toscana",
  "provinceSlug": "firenze",
  "citySlug": "firenze",
  "transaction": "sale",
  "propertyType": "apartment",
  "areaMin": 60,
  "roomsMin": 2,
  "maxListings": 400
}
```

Then:

```bash
apify call logiover/subito-it-property-scraper --input-file=input.json
```

## Download the dataset

```bash
apify runs ls
apify datasets get-items <DATASET_ID> --format=csv > subito-listings.csv
apify datasets get-items <DATASET_ID> --format=json > subito-listings.json
```

> Tip: target nationwide with `regionSlug: "italia"`, or drill down region → province → city. Schedule recurring runs from the **Schedules** tab to monitor prices and new listings.
