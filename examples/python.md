# Subito.it Property Scraper — Python examples

Call the [Subito.it Property Scraper](https://apify.com/logiover/subito-it-property-scraper) from Python with the official [`apify-client`](https://pypi.org/project/apify-client/).

## Install

```bash
pip install apify-client
```

## Apartments for sale in Rome (filtered)

```python
from apify_client import ApifyClient

client = ApifyClient("YOUR_API_TOKEN")

run = client.actor("logiover/subito-it-property-scraper").call(run_input={
    "regionSlug": "lazio",
    "provinceSlug": "roma",
    "citySlug": "roma",
    "transaction": "sale",
    "propertyType": "apartment",
    "priceMin": 150000,
    "priceMax": 400000,
    "maxListings": 300,
})

for p in client.dataset(run["defaultDatasetId"]).iterate_items():
    print(p.get("price"), "EUR |", p.get("pricePerSqm"), "EUR/m² |", p.get("microLocation"))
```

## €/m² analysis with pandas

```python
import pandas as pd
from apify_client import ApifyClient

client = ApifyClient("YOUR_API_TOKEN")

run = client.actor("logiover/subito-it-property-scraper").call(run_input={
    "regionSlug": "lombardia",
    "provinceSlug": "milano",
    "citySlug": "milano",
    "transaction": "sale",
    "propertyType": "apartment",
    "maxListings": 1000,
})

rows = list(client.dataset(run["defaultDatasetId"]).iterate_items())
df = pd.DataFrame(rows)
df["pricePerSqm"] = pd.to_numeric(df["pricePerSqm"], errors="coerce")

print(df.groupby("microLocation")["pricePerSqm"].mean().round(0).sort_values(ascending=False).head(15))
```

## Private-seller leads → CSV

```python
from apify_client import ApifyClient

client = ApifyClient("YOUR_API_TOKEN")

run = client.actor("logiover/subito-it-property-scraper").call(run_input={
    "regionSlug": "campania",
    "provinceSlug": "napoli",
    "transaction": "sale",
    "advertiserType": "private",
    "maxListings": 500,
})

with open("subito-private-sellers.csv", "wb") as f:
    f.write(client.dataset(run["defaultDatasetId"]).download_items(item_format="csv"))

print("Saved subito-private-sellers.csv")
```

## Read token from an environment variable

```python
import os
from apify_client import ApifyClient

client = ApifyClient(os.environ["APIFY_TOKEN"])

run = client.actor("logiover/subito-it-property-scraper").call(run_input={
    "regionSlug": "toscana", "transaction": "sale", "propertyType": "apartment", "maxListings": 200,
})
items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
print(len(items), "Tuscany apartments")
```

> Keep your token in `APIFY_TOKEN` or a secrets manager instead of committing it.
