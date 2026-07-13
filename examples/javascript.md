# Subito.it Property Scraper — JavaScript / Node.js examples

Call the [Subito.it Property Scraper](https://apify.com/logiover/subito-it-property-scraper) from Node.js with the official [`apify-client`](https://www.npmjs.com/package/apify-client).

## Install

```bash
npm install apify-client
```

## Apartments for sale in Rome (filtered)

```js
import { ApifyClient } from 'apify-client';

const client = new ApifyClient({ token: 'YOUR_API_TOKEN' });

const run = await client.actor('logiover/subito-it-property-scraper').call({
  regionSlug: 'lazio',
  provinceSlug: 'roma',
  citySlug: 'roma',
  transaction: 'sale',
  propertyType: 'apartment',
  priceMin: 150000,
  priceMax: 400000,
  maxListings: 300,
});

const { items } = await client.dataset(run.defaultDatasetId).listItems();
console.log(`Got ${items.length} listings`);
console.table(items.slice(0, 10).map((p) => ({
  price: p.price,
  eurPerSqm: p.pricePerSqm,
  rooms: p.rooms,
  city: p.city,
})));
```

## Average €/m² by micro-location

```js
import { ApifyClient } from 'apify-client';

const client = new ApifyClient({ token: 'YOUR_API_TOKEN' });

const run = await client.actor('logiover/subito-it-property-scraper').call({
  regionSlug: 'lombardia',
  provinceSlug: 'milano',
  citySlug: 'milano',
  transaction: 'sale',
  propertyType: 'apartment',
  maxListings: 1000,
});

const { items } = await client.dataset(run.defaultDatasetId).listItems();

const byZone = {};
for (const p of items) {
  const v = Number(p.pricePerSqm);
  if (!p.microLocation || !Number.isFinite(v)) continue;
  (byZone[p.microLocation] ??= []).push(v);
}
for (const [zone, vals] of Object.entries(byZone)) {
  const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
  console.log(`${zone}: €${Math.round(avg)}/m² (${vals.length})`);
}
```

## Private-seller leads → CSV

```js
import { ApifyClient } from 'apify-client';
import { writeFileSync } from 'node:fs';

const client = new ApifyClient({ token: 'YOUR_API_TOKEN' });

const run = await client.actor('logiover/subito-it-property-scraper').call({
  regionSlug: 'campania',
  provinceSlug: 'napoli',
  transaction: 'sale',
  advertiserType: 'private',
  maxListings: 500,
});

const csv = await client.dataset(run.defaultDatasetId).downloadItems('csv');
writeFileSync('subito-private-sellers.csv', csv);
console.log('Saved subito-private-sellers.csv');
```

## CommonJS variant

```js
const { ApifyClient } = require('apify-client');

(async () => {
  const client = new ApifyClient({ token: process.env.APIFY_TOKEN });
  const run = await client.actor('logiover/subito-it-property-scraper').call({
    regionSlug: 'toscana', transaction: 'sale', propertyType: 'apartment', maxListings: 200,
  });
  const { items } = await client.dataset(run.defaultDatasetId).listItems();
  console.log(items.length, 'Tuscany apartments');
})();
```

> Store your token in `process.env.APIFY_TOKEN` rather than hard-coding it.
