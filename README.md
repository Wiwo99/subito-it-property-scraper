# Casa Radar — Subito.it scraper (immobili & motori) + dashboard

> Fork di [logiover/subito-it-property-scraper](https://github.com/logiover/subito-it-property-scraper).
> Il repository originale contiene **solo documentazione** per un actor Apify a pagamento e nessun codice.
> Questo fork è uno scraper **open source e completo**, con lo stesso schema di campi del README originale, più
> ricerche salvate per parole chiave, storico prezzi, notifiche e una dashboard statica.

*English: open-source Subito.it scraper for real estate **and vehicles** (no API key, no Apify). Keyword "watches", SQLite history,
price-drop detection, Telegram/webhook alerts, static dashboard, GitHub Actions scheduling. Commands are English,
docs are Italian.*

---

## Cosa fa

- **Scraping diretto** dell'API pubblica usata dal sito (`hades.subito.it`): niente login, niente API key, niente browser.
- **Immobili e Motori**: appartamenti, ville, terreni… e auto, moto, veicoli commerciali, camper, nautica.
- **Watch per parole chiave e filtri** (`watches.json`): per ogni ricerca salvata definisci zona, categoria, vendita/affitto,
  prezzo, privato/agenzia, parole chiave (con esclusioni, AND, wildcard) e, per i veicoli, marca, modello, carburante,
  cambio, carrozzeria, anno, km, CV, stato (usato/Km0/nuovo), neopatentati, cilindrata.
- **Storico in SQLite**: dedup, prima/ultima vista, storico prezzi, ribassi, annunci nuovi rispetto al giro precedente.
- **Dashboard statica** (`docs/index.html`): un solo file HTML con i dati incorporati. Si apre da `file://`,
  da GitHub Pages o da qualunque hosting statico. Nessun server locale.
- **Notifiche** Telegram o webhook JSON per i nuovi annunci e le variazioni di prezzo.
- **Automazione**: workflow GitHub Actions ogni 3 ore (commit del DB e della dashboard) oppure `launchd` su macOS.
- **Export** CSV / JSON / JSONL / XLSX con i campi dello schema originale (`adId`, `detailUrl`, `pricePerSqm`, …).

## Installazione

Serve Python ≥ 3.9. Con [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/Wiwo99/subito-it-property-scraper.git
cd subito-it-property-scraper
uv sync                    # oppure: pip install -e .
uv run subito --help
```

## Uso rapido

```bash
# ricerca una tantum, output tabellare
uv run subito search -r lombardia -p bergamo -q terrazzo -q attico -x asta --price-max 300000 -n 50

# export
uv run subito search -r lazio -p roma -t rent -q arredato -o roma-affitti.csv

# motori
uv run subito search -c auto -r lombardia --brand Volkswagen --model Golf --fuel diesel --gearbox automatico --year-min 2017 --km-max 130000 --price-max 18000
uv run subito search -c moto --brand Yamaha --model "Ténéré 700" --price-max 9500
uv run subito values brands -c auto            # marche come le conosce Subito
uv run subito values models -c auto --brand Fiat
uv run subito values fuel                       # carburanti, cambi (gearbox), car_type, motorbike_type, vehicle_status…

# codici regione / categorie
uv run subito regions
uv run subito geo lombardia bergamo treviglio
```

## Ricerche automatiche (watch)

Modifica `watches.json`:

```json
{
  "defaults": { "max_items": 300, "category": "appartamenti", "transaction": "sale" },
  "watches": [
    {
      "id": "bilocale-milano",
      "name": "Bilocale Milano",
      "region": "lombardia",
      "province": "milano",
      "keywords": ["bilocale", "2 locali"],
      "exclude": ["asta", "nuda proprietà"],
      "price_max": 260000,
      "size_min": 40
    }
  ]
}
```

| Chiave | Significato |
|---|---|
| `region`, `province`, `town` | slug o nome (es. `lombardia`, `bergamo`, `treviglio`), risolti via API geo di Subito e cachati in `data/geo_cache.json`. Ometti `region` per tutta Italia. |
| `category` | immobili: `appartamenti`, `ville`, `terreni`, `garage`, `loft`, `uffici`, `camere`, `vacanze` · motori: `auto`, `moto`, `veicoli-commerciali`, `camper`, `nautica`, `accessori-auto`, `accessori-moto` |
| `transaction` | `sale` (vendita), `rent` (affitto), `wanted` (cercasi) |
| `keywords` | lista, **OR**: basta che una compaia. Ogni keyword viene anche inviata a Subito come ricerca full-text. Supporta frasi (`"2 locali"`) e wildcard finale (`ristruttur*`). |
| `all` | lista, **AND**: devono comparire tutte |
| `exclude` | lista, **NOT**: se compare una, l'annuncio è scartato |
| `title_only` | cerca solo nel titolo |
| `price_min/max`, `size_min/max`, `rooms_min/max` | range numerici (applicati anche lato Subito) |
| `brand`, `model` | veicoli: marca e modello per nome (`Volkswagen`, `Golf`). Modello ambiguo (più generazioni) → cercato in full-text |
| `fuel`, `gearbox`, `body_type`, `vehicle_status` | `diesel`/`benzina`/`gpl`/`metano`/`elettrica`/`ibrida` · `manuale`/`automatico` · auto: `utilitaria`/`berlina`/`station wagon`/`suv`/`monovolume`/`cabrio`; moto: `sport`/`enduro`/`naked`/`scooter`/`custom`/`turismo` · `usato`/`km0`/`nuovo` |
| `year_min/max`, `km_min/max`, `hp_min/max`, `cc_min/max` | anno, chilometri, CV, cilindrata (moto) |
| `new_drivers` | `true` = solo auto per neopatentati |
| `vehicle_color`, `pollution` | colore veicolo (`bianco`, `nero`…), classe emissioni (`Euro 6`) |
| `advertiser` | `private` o `agency` |
| `max_items` | massimo annunci per keyword (default 300) |
| `enabled`, `color`, `query` | disattiva la watch, colore nella dashboard, query esplicita da inviare al posto delle keyword |

Il matching locale ignora accenti e maiuscole ed è a **parola intera**: `bilocale` non matcha `bilocalexyz`.
I filtri veicolo vengono inviati a Subito (chiavi risolte via `hades.subito.it/v1/values`, cache in `data/values_cache.json`)
e ricontrollati in locale. La dashboard mostra solo gli annunci delle watch attive (`enabled: true`); `subito build --all` include il resto.

Esempio motori:

```json
{
  "id": "golf-diesel-automatica",
  "name": "Golf diesel automatica",
  "region": "lombardia",
  "category": "auto",
  "brand": "Volkswagen", "model": "Golf",
  "fuel": "diesel", "gearbox": "automatico",
  "year_min": 2017, "km_max": 130000, "price_max": 18000,
  "exclude": ["incidentata", "ricambi"]
}
```

```bash
uv run subito run --build            # esegue tutte le watch e rigenera docs/index.html
uv run subito run --only bilocale-milano
uv run subito watches                # lista watch e conteggi
uv run subito build                  # rigenera solo la dashboard dal DB
uv run subito export -o tutti.xlsx   # richiede: uv sync --extra xlsx
open docs/index.html
```

## Dashboard

`docs/index.html` è autonoma e mobile-first (Material 3, tema chiaro/scuro):

- chip per ogni watch con conteggio e badge **+nuovi**, indicatore che scorre tra le voci
- ricerca istantanea per parole chiave (tutte le parole, con evidenziazione), opzione "solo nel titolo"
- filtri che si adattano ai dati: immobili (mq, locali, categoria) e motori (marca, modello, carburante, cambio, carrozzeria, anno, km, CV, stato, neopatentati), più vendita/affitto, privato/concessionario, prezzo, provincia, comune
- ordinamento per data, prezzo, €/mq, superficie, km, anno; mediana €/mq o prezzo mediano del risultato corrente
- badge **Nuovo** (comparso dopo il giro precedente), **ribasso/rialzo** con prezzo precedente barrato
- preferiti e "nascondi annuncio" (salvati nel browser), scheda dettaglio con galleria, storico prezzo, link mappa e Subito

Con GitHub Pages attivo su `docs/` la dashboard è online a `https://<utente>.github.io/subito-it-property-scraper/`.

## Automazione

### GitHub Actions (consigliato)

`.github/workflows/scrape.yml` gira ogni 3 ore (`workflow_dispatch` per lanciarlo a mano): esegue le watch, ricostruisce
la dashboard, esegue i test e committa `data/subito.db` + `docs/`. Abilita **Settings → Pages → Deploy from branch → `/docs`**.

Secret opzionali: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `NOTIFY_WEBHOOK_URL`.

> Subito.it può limitare gli IP dei datacenter. Il client fa retry con backoff e il workflow usa `--delay 1.2`;
> se vedi errori 403/429 costanti, passa a `launchd`/cron da una rete residenziale.

### launchd (macOS)

```bash
sed "s#__REPO__#$PWD#g" scripts/it.casaradar.scrape.plist > ~/Library/LaunchAgents/it.casaradar.scrape.plist
launchctl load ~/Library/LaunchAgents/it.casaradar.scrape.plist
```

### Notifiche Telegram

```bash
export TELEGRAM_BOT_TOKEN=...   # da @BotFather
export TELEGRAM_CHAT_ID=...     # id chat o canale
uv run subito run --notify
```

## Campi esportati

Stesso schema del README originale più alcuni extra:

`adId`, `urn`, `detailUrl`, `title`, `shortDescription`, `description`, `transactionType`, `propertyType`, `categoryId`,
`categoryLabel`, `advertType`, `price`, `priceCurrency`, `pricePerSqm`, `areaSqm`, `terrainAreaSqm`, `rooms`, `roomsLabel`,
`bathrooms`, `floor`, `buildingCondition`, `heatingType`, `energyClass`, `hasElevator`, `hasParking`, `parkingType`,
`hasBalcony`, `hasGarden`, `hasAirConditioning`, `isFurnished`, `isLastFloor`, `isMultiLevel`, `hasReception`,
`isAvailableNow`, `isShortRental`, `roomType`, `country`, `region`, `regionId`, `province`, `provinceId`, `provinceCode`,
`city`, `cityIstat`, `microLocation`, `fullAddress`, `latitude`, `longitude`, `mainImageUrl`, `imageUrls`, `imageCount`,
`advertiserId`, `advertiserName`, `advertiserType`, `advertiserShopId`, `datePosted`, `dateExpiration`, `scrapedAt`,
`searchRegion`, `searchProvince`, `searchTown`, `searchKeyword`, `searchWatch`.

Veicoli (`domain: motori`): `brand`, `model`, `modelFull`, `version`, `year`, `registerDate`, `mileageKm`, `mileageRange`, `fuel`,
`gearbox`, `bodyType`, `doors`, `seats`, `color`, `pollution`, `powerKw`, `powerCv`, `vehicleStatus`, `forNewDrivers`,
`vatDeductible`, `warrantyMonths`, `itemCondition`, `shipLength`, `isShippable`.

## Struttura

```
subito_scraper/
  api.py        client HTTP (throttle, retry, paginazione)
  geo.py        regioni statiche, province/comuni via API geo, cachati
  values.py     marche/modelli/carburanti/cambi/fasce km -> chiavi Subito, cachati
  models.py     normalizzazione annuncio -> record piatto
  watches.py    watch, matching keyword, esecuzione
  store.py      SQLite: listings, price_history, watch_matches, runs
  export.py     CSV / JSON / JSONL / XLSX
  notify.py     Telegram + webhook
  dashboard.py  genera docs/index.html dal template
  cli.py        comando `subito`
dashboard/template.html   UI (vanilla JS, lucide icons)
watches.json              ricerche salvate
docs/                     dashboard generata (GitHub Pages)
data/subito.db            database
```

## Test

```bash
uv run --extra dev pytest -q
```

## Note legali

Progetto personale a scopo di studio. Rispetta i termini di servizio di Subito.it: usa un `--delay` ragionevole,
non ridistribuire i dati e non usare le informazioni degli inserzionisti per contatti non richiesti.

Licenza MIT.
