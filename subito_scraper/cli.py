"""Command line interface: ``subito --help``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .api import SubitoClient
from .dashboard import build as build_dashboard
from .export import FORMATS, export
from .geo import REGIONS, GeoResolver
from .models import ADVERTISER_TYPES, CATEGORIES, ad_type_key, category_id, normalize
from .notify import notify
from .store import Store
from .watches import Watch, load_watches, run_all

DEFAULT_DB = Path("data/subito.db")
DEFAULT_WATCHES = Path("watches.json")
DEFAULT_DASHBOARD = Path("docs/index.html")
GEO_CACHE = Path("data/geo_cache.json")


def _client(args: argparse.Namespace) -> SubitoClient:
    return SubitoClient(delay=args.delay)


def _geo(client: SubitoClient) -> GeoResolver:
    return GeoResolver(client, GEO_CACHE)


# ----------------------------------------------------------------- commands
def cmd_search(args: argparse.Namespace) -> int:
    client = _client(args)
    geo = _geo(client)
    watch = Watch(
        id="cli",
        name="cli",
        region=args.region,
        province=args.province,
        town=args.town,
        category=args.category,
        transaction=args.transaction,
        keywords=args.keyword or [],
        exclude=args.exclude or [],
        title_only=args.title_only,
        price_min=args.price_min,
        price_max=args.price_max,
        size_min=args.size_min,
        size_max=args.size_max,
        rooms_min=args.rooms_min,
        rooms_max=args.rooms_max,
        advertiser=args.advertiser,
        max_items=args.max,
    )
    base = watch.api_params(geo)
    records: List[Dict[str, Any]] = []
    seen = set()
    for query in watch.queries():
        params = dict(base)
        if query:
            params["q"] = query
        for ad in client.iter_ads(params, max_items=args.max):
            rec = normalize(ad, search={"region": args.region, "province": args.province, "town": args.town, "query": query})
            if rec["adId"] in seen or not watch.matches(rec):
                continue
            seen.add(rec["adId"])
            records.append(rec)
    if args.out:
        path = export(records, Path(args.out), args.format or "")
        print(f"{len(records)} listings -> {path}")
    else:
        if args.format == "json":
            print(json.dumps(records, ensure_ascii=False, indent=1))
        else:
            for rec in records:
                price = f"{rec['price']:>9,} €".replace(",", ".") if rec.get("price") else "      n.d."
                sqm = f"{rec['pricePerSqm']:>5} €/mq" if rec.get("pricePerSqm") else "          "
                print(f"{price} {sqm}  {rec.get('areaSqm') or '?':>4} mq  {rec.get('city') or '':<22} {rec['title'][:60]}  {rec['detailUrl']}")
            print(f"-- {len(records)} listings, {client.requests_made} requests", file=sys.stderr)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    watches = load_watches(Path(args.watches))
    if args.only:
        watches = [w for w in watches if w.id in set(args.only)]
        if not watches:
            print(f"no watch matches --only {args.only}", file=sys.stderr)
            return 2
    client = _client(args)
    geo = _geo(client)
    results = []
    with Store(Path(args.db)) as store:
        for res in run_all(watches, client, geo, store):
            results.append(res)
            status = f"ERROR {res.error}" if res.error else f"{res.matched} matched, {len(res.new)} new, {len(res.price_changes)} price changes"
            print(f"[{res.watch.id}] fetched {res.fetched}: {status}")
        if args.prune_days:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=args.prune_days)).isoformat(timespec="seconds")
            removed = store.prune(cutoff)
            print(f"pruned {removed} listings not seen for {args.prune_days} days")
        if args.notify:
            print("notify:", notify(results))
        if args.build:
            out = build_dashboard(store, watches, Path(args.dashboard))
            print(f"dashboard -> {out}")
        counts = store.counts()
    print(f"done: {counts['listings']} listings in db, {client.requests_made} requests")
    return 1 if any(r.error for r in results) and not args.ignore_errors else 0


def cmd_build(args: argparse.Namespace) -> int:
    watches = load_watches(Path(args.watches)) if Path(args.watches).exists() else []
    with Store(Path(args.db)) as store:
        out = build_dashboard(store, watches, Path(args.dashboard))
    print(f"dashboard -> {out}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    with Store(Path(args.db)) as store:
        records = store.listings(watch_id=args.watch)
    path = export(records, Path(args.out), args.format or "")
    print(f"{len(records)} listings -> {path}")
    return 0


def cmd_geo(args: argparse.Namespace) -> int:
    client = _client(args)
    geo = _geo(client)
    print(json.dumps(geo.resolve(args.region, args.province, args.town), ensure_ascii=False, indent=1))
    return 0


def cmd_watches(args: argparse.Namespace) -> int:
    watches = load_watches(Path(args.watches))
    counts: Dict[str, int] = {}
    if Path(args.db).exists():
        with Store(Path(args.db)) as store:
            for ad_id, ms in store.matches_by_listing().items():
                for m in ms:
                    counts[m["watchId"]] = counts.get(m["watchId"], 0) + 1
    for w in watches:
        flag = "" if w.enabled else " (disabled)"
        print(f"{w.id:<28} {counts.get(w.id, 0):>5}  {w.name}{flag}\n{'':<28}        {w.summary()}")
    return 0


def cmd_regions(_: argparse.Namespace) -> int:
    for slug, (rid, name) in REGIONS.items():
        print(f"{rid:>2}  {slug:<24} {name}")
    print("\ncategories:")
    for cid, (label, eng, slug) in CATEGORIES.items():
        print(f"{cid:>2}  {slug:<28} {eng:<12} {label}")
    print("\ntransactions: sale (vendita), rent (affitto), wanted (cercasi)")
    return 0


# -------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="subito", description="Subito.it real-estate scraper with keyword watches")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    parser.add_argument("--delay", type=float, default=0.7, help="seconds between requests (default 0.7)")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="one-off search, print or export")
    s.add_argument("-r", "--region", help="region slug, e.g. lombardia (omit for all Italy)")
    s.add_argument("-p", "--province", help="province name/slug, e.g. bergamo")
    s.add_argument("--town", help="town name/slug (needs --region, optionally --province)")
    s.add_argument("-c", "--category", default="appartamenti", help="appartamenti|ville|terreni|garage|loft|uffici|camere|vacanze")
    s.add_argument("-t", "--transaction", default="sale", help="sale|rent|wanted")
    s.add_argument("-q", "--keyword", action="append", help="keyword (repeatable, OR)")
    s.add_argument("-x", "--exclude", action="append", help="exclude keyword (repeatable)")
    s.add_argument("--title-only", action="store_true")
    s.add_argument("--price-min", type=int)
    s.add_argument("--price-max", type=int)
    s.add_argument("--size-min", type=int)
    s.add_argument("--size-max", type=int)
    s.add_argument("--rooms-min", type=int)
    s.add_argument("--rooms-max", type=int)
    s.add_argument("--advertiser", choices=sorted(ADVERTISER_TYPES))
    s.add_argument("-n", "--max", type=int, default=100, help="max listings per keyword (default 100)")
    s.add_argument("-o", "--out", help="output file (.csv/.json/.jsonl/.xlsx)")
    s.add_argument("-f", "--format", choices=FORMATS + ("table",), help="output format (default: from extension / table)")
    s.set_defaults(func=cmd_search)

    r = sub.add_parser("run", help="run all watches, store results, optionally notify and build dashboard")
    r.add_argument("-w", "--watches", default=str(DEFAULT_WATCHES))
    r.add_argument("--db", default=str(DEFAULT_DB))
    r.add_argument("--only", nargs="+", help="run only these watch ids")
    r.add_argument("--notify", action="store_true", help="send Telegram/webhook alerts for new matches")
    r.add_argument("--build", action="store_true", help="rebuild the dashboard afterwards")
    r.add_argument("--dashboard", default=str(DEFAULT_DASHBOARD))
    r.add_argument("--prune-days", type=int, default=0, help="drop listings not seen for N days (0 = keep all)")
    r.add_argument("--ignore-errors", action="store_true", help="exit 0 even if a watch failed")
    r.set_defaults(func=cmd_run)

    b = sub.add_parser("build", help="rebuild the static dashboard from the database")
    b.add_argument("-w", "--watches", default=str(DEFAULT_WATCHES))
    b.add_argument("--db", default=str(DEFAULT_DB))
    b.add_argument("--dashboard", default=str(DEFAULT_DASHBOARD))
    b.set_defaults(func=cmd_build)

    e = sub.add_parser("export", help="export stored listings")
    e.add_argument("--db", default=str(DEFAULT_DB))
    e.add_argument("--watch", help="only listings matched by this watch id")
    e.add_argument("-o", "--out", required=True)
    e.add_argument("-f", "--format", choices=FORMATS)
    e.set_defaults(func=cmd_export)

    g = sub.add_parser("geo", help="resolve region/province/town to Subito ids")
    g.add_argument("region")
    g.add_argument("province", nargs="?")
    g.add_argument("town", nargs="?")
    g.set_defaults(func=cmd_geo)

    w = sub.add_parser("watches", help="list watches and match counts")
    w.add_argument("-w", "--watches", default=str(DEFAULT_WATCHES))
    w.add_argument("--db", default=str(DEFAULT_DB))
    w.set_defaults(func=cmd_watches)

    sub.add_parser("regions", help="list region and category codes").set_defaults(func=cmd_regions)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    # validate enums early for friendlier errors
    if getattr(args, "category", None):
        category_id(args.category)
    if getattr(args, "transaction", None):
        ad_type_key(args.transaction)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
