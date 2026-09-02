"""Saved searches ("watches") driven by keywords.

A watch describes *where* to look (region/province/town, category,
transaction, price/size ranges…) and *what* to look for (keywords). Each
keyword is sent to Subito as a full-text query, then results are filtered
locally again with word-boundary matching, ``all`` (AND) keywords and
``exclude`` (NOT) keywords, so the matching is stricter and predictable."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set

from .api import SubitoClient
from .geo import GeoResolver
from .models import ADVERTISER_TYPES, ad_type_key, category_id, normalize, record_text
from .store import Store, utcnow

log = logging.getLogger(__name__)


@dataclass
class Watch:
    id: str
    name: str
    region: Optional[str] = None
    province: Optional[str] = None
    town: Optional[str] = None
    category: str = "appartamenti"
    transaction: str = "sale"
    keywords: List[str] = field(default_factory=list)
    all: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    title_only: bool = False
    query: Optional[str] = None
    price_min: Optional[int] = None
    price_max: Optional[int] = None
    size_min: Optional[int] = None
    size_max: Optional[int] = None
    rooms_min: Optional[int] = None
    rooms_max: Optional[int] = None
    advertiser: Optional[str] = None
    max_items: int = 300
    enabled: bool = True
    color: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: Dict[str, Any], defaults: Optional[Dict[str, Any]] = None) -> "Watch":
        data = dict(defaults or {})
        data.update(raw)
        if "id" not in data:
            data["id"] = re.sub(r"[^a-z0-9]+", "-", str(data.get("name", "watch")).lower()).strip("-")
        data.setdefault("name", data["id"])
        for key in ("keywords", "all", "exclude"):
            value = data.get(key)
            if isinstance(value, str):
                data[key] = [value]
            elif value is None:
                data[key] = []
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        unknown = set(data) - known
        if unknown:
            log.warning("watch '%s': ignoring unknown keys %s", data["id"], sorted(unknown))
        return cls(**{k: v for k, v in data.items() if k in known})

    # ------------------------------------------------------------- params
    def api_params(self, geo: GeoResolver) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "c": category_id(self.category),
            "t": ad_type_key(self.transaction),
        }
        params.update({k: v for k, v in geo.resolve(self.region, self.province, self.town).items() if k in ("r", "ci", "to")})
        if self.price_min is not None:
            params["ps"] = self.price_min
        if self.price_max is not None:
            params["pe"] = self.price_max
        if self.size_min is not None:
            params["szs"] = self.size_min
        if self.size_max is not None:
            params["sze"] = self.size_max
        if self.rooms_min is not None:
            params["rs"] = self.rooms_min
        if self.rooms_max is not None:
            params["re"] = self.rooms_max
        if self.advertiser:
            params["advt"] = ADVERTISER_TYPES[self.advertiser.lower()]
        if self.title_only:
            params["qso"] = "true"
        return params

    def queries(self) -> List[Optional[str]]:
        """Distinct full-text queries to send. One per keyword, or a single
        explicit ``query``; ``None`` means "no text filter"."""
        if self.query:
            return [self.query]
        if self.keywords:
            seen: Set[str] = set()
            out: List[Optional[str]] = []
            for kw in self.keywords:
                norm = normalize_text(kw)
                if norm and norm not in seen:
                    seen.add(norm)
                    out.append(kw)
            return out
        return [None]

    # ----------------------------------------------------------- matching
    def matches(self, record: Dict[str, Any]) -> bool:
        haystack = normalize_text(record.get("title") or "" if self.title_only else record_text(record))
        if self.exclude and any(contains(haystack, kw) for kw in self.exclude):
            return False
        if self.all and not all(contains(haystack, kw) for kw in self.all):
            return False
        if self.keywords and not any(contains(haystack, kw) for kw in self.keywords):
            return False
        # numeric guards: Subito applies ranges server-side, but ads without a
        # value slip through, so enforce locally when the user asked for a range.
        price = record.get("price")
        if self.price_min is not None and (price is None or price < self.price_min):
            return False
        if self.price_max is not None and (price is None or price > self.price_max):
            return False
        area = record.get("areaSqm")
        if self.size_min is not None and area is not None and area < self.size_min:
            return False
        if self.size_max is not None and area is not None and area > self.size_max:
            return False
        rooms = record.get("rooms")
        if self.rooms_min is not None and rooms is not None and rooms < self.rooms_min:
            return False
        if self.rooms_max is not None and rooms is not None and rooms > self.rooms_max:
            return False
        if self.advertiser and record.get("advertType") != ("agency" if ADVERTISER_TYPES[self.advertiser.lower()] else "private"):
            return False
        return True

    def summary(self) -> str:
        place = " / ".join(p for p in (self.region, self.province, self.town) if p) or "Italia"
        bits = [self.transaction, self.category, place]
        if self.keywords:
            bits.append("kw: " + ", ".join(self.keywords))
        if self.price_min is not None or self.price_max is not None:
            bits.append(f"€ {self.price_min or 0}–{self.price_max or '∞'}")
        return " · ".join(bits)


# ------------------------------------------------------------------ helpers
def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", text).strip()


def contains(haystack: str, keyword: str) -> bool:
    """Word-boundary phrase match. ``bilocale`` matches "bilocale," but not
    "bilocalexyz". Supports a trailing ``*`` wildcard (``ristruttur*``)."""
    kw = normalize_text(keyword)
    if not kw:
        return False
    if kw.endswith("*"):
        pattern = r"\b" + re.escape(kw[:-1])
    else:
        pattern = r"\b" + re.escape(kw) + r"\b"
    return re.search(pattern, haystack) is not None


def load_watches(path: Path) -> List[Watch]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, list):
        raw = {"watches": raw}
    defaults = raw.get("defaults") or {}
    watches = [Watch.from_dict(w, defaults) for w in raw.get("watches", [])]
    ids = [w.id for w in watches]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate watch ids: {sorted(dupes)}")
    return watches


# ---------------------------------------------------------------- running
@dataclass
class WatchResult:
    watch: Watch
    fetched: int = 0
    matched: int = 0
    new: List[Dict[str, Any]] = field(default_factory=list)
    price_changes: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


def run_watch(watch: Watch, client: SubitoClient, geo: GeoResolver, store: Store, now: Optional[str] = None) -> WatchResult:
    now = now or utcnow()
    result = WatchResult(watch=watch)
    run_id = store.start_run(watch.id)
    seen_ids: Set[str] = set()
    try:
        base_params = watch.api_params(geo)
        for query in watch.queries():
            params = dict(base_params)
            if query:
                params["q"] = query
            log.info("[%s] searching %s", watch.id, params)
            for ad in client.iter_ads(params, max_items=watch.max_items):
                result.fetched += 1
                record = normalize(
                    ad,
                    search={"region": watch.region, "province": watch.province, "town": watch.town, "query": query, "watch": watch.id},
                    scraped_at=now,
                )
                if record["adId"] in seen_ids or not watch.matches(record):
                    continue
                seen_ids.add(record["adId"])
                result.matched += 1
                status, previous = store.upsert_listing(record, now)
                is_new_match = store.record_match(watch.id, record["adId"], now)
                if is_new_match and status == "new":
                    result.new.append(record)
                elif status == "price_changed":
                    result.price_changes.append({**record, "previousPrice": previous})
        store.finish_run(
            run_id,
            fetched=result.fetched,
            matched=result.matched,
            new_count=len(result.new),
            price_changes=len(result.price_changes),
        )
    except Exception as exc:  # noqa: BLE001 - keep other watches running
        log.exception("[%s] failed", watch.id)
        result.error = str(exc)
        store.finish_run(run_id, fetched=result.fetched, matched=result.matched, error=str(exc))
    store.commit()
    return result


def run_all(watches: List[Watch], client: SubitoClient, geo: GeoResolver, store: Store) -> Iterator[WatchResult]:
    now = utcnow()
    run_id = store.start_run(None)
    totals = {"fetched": 0, "matched": 0, "new_count": 0, "price_changes": 0}
    for watch in watches:
        if not watch.enabled:
            log.info("[%s] disabled, skipping", watch.id)
            continue
        result = run_watch(watch, client, geo, store, now)
        totals["fetched"] += result.fetched
        totals["matched"] += result.matched
        totals["new_count"] += len(result.new)
        totals["price_changes"] += len(result.price_changes)
        yield result
    store.finish_run(run_id, **totals)
    store.commit()
