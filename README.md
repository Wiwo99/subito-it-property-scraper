# Casa Radar — Subito.it real-estate scraper + dashboard

> Fork di [logiover/subito-it-property-scraper](https://github.com/logiover/subito-it-property-scraper).
> Il repository originale contiene **solo documentazione** per un actor Apify a pagamento e nessun codice.
> Questo fork è uno scraper **open source e completo**, con lo stesso schema di campi del README originale, più
> ricerche salvate per parole chiave, storico prezzi, notifiche e una dashboard statica.

*English: open-source Subito.it property scraper (no API key, no Apify). Keyword "watches", SQLite history,
price-drop detection, Telegram/webhook alerts, static dashboard, GitHub Actions scheduling. Commands are English,
docs are Italian.*

---

## Cosa fa

- **Scraping diretto** dell'API pubblica usata dal sito (`hades.subito.it`): niente login, niente API key, niente browser.
- **Watch per parole chiave** (`watches.json`): per ogni ricerca salvata definisci zona, categoria, vendita/affitto,
  range di prezzo/mq/locali, privato/agenzia e le parole chiave da cercare (con esclusioni, AND, wildcard).
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
| `category` | `appartamenti`, `ville`, `terreni`, `garage`, `loft`, `uffici`, `camere`, `vacanze` |
| `transaction` | `sale` (vendita), `rent` (affitto), `wanted` (cercasi) |
| `keywords` | lista, **OR**: basta che una compaia. Ogni keyword viene anche inviata a Subito come ricerca full-text. Supporta frasi (`"2 locali"`) e wildcard finale (`ristruttur*`). |
| `all` | lista, **AND**: devono comparire tutte |
| `exclude` | lista, **NOT**: se compare una, l'annuncio è scartato |
| `title_only` | cerca solo nel titolo |
| `price_min/max`, `size_min/max`, `rooms_min/max` | range numerici (applicati anche lato Subito) |
| `advertiser` | `private` o `agency` |
| `max_items` | massimo annunci per keyword (default 300) |
| `enabled`, `color`, `query` | disattiva la watch, colore nella dashboard, query esplicita da inviare al posto delle keyword |

Il matching locale ignora accenti e maiuscole ed è a **parola intera**: `bilocale` non matcha `bilocalexyz`.

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
- filtri: vendita/affitto, privato/agenzia, prezzo, mq, locali, categoria, provincia, comune
- ordinamento per data, prezzo, €/mq, superficie; mediana €/mq del risultato corrente
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

## Struttura

```
subito_scraper/
  api.py        client HTTP (throttle, retry, paginazione)
  geo.py        regioni statiche, province/comuni via API geo, cachati
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
