"""Saved searches ("watches") driven by keywords and structured filters.

A watch describes *where* to look (region/province/town, category,
transaction, price range…), *what* to look for (keywords) and, for vehicles,
the usual filters (brand, model, fuel, gearbox, year, km, power, status).
Keywords are sent to Subito as full-text queries, then every result is
re-checked locally with word-boundary matching, ``all`` (AND) and
``exclude`` (NOT) lists, so matching is strict and predictable."""

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
from .models import ADVERTISER_TYPES, VEHICLE_IDS, ad_type_key, category_id, domain_of, normalize, record_text
from .store import Store, utcnow
from .values import ValuesResolver

log = logging.getLogger(__name__)

VEHICLE_FIELDS = (
    "brand", "model", "fuel", "gearbox", "body_type", "vehicle_status", "year_min", "year_max",
    "km_min", "km_max", "hp_min", "hp_max", "new_drivers", "color", "pollution", "cc_min", "cc_max",
)


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
    # real estate
    size_min: Optional[int] = None
    size_max: Optional[int] = None
    rooms_min: Optional[int] = None
    rooms_max: Optional[int] = None
    # vehicles
    brand: Optional[str] = None
    model: Optional[str] = None
    fuel: Optional[str] = None
    gearbox: Optional[str] = None
    body_type: Optional[str] = None
    vehicle_status: Optional[str] = None
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    km_min: Optional[int] = None
    km_max: Optional[int] = None
    hp_min: Optional[int] = None
    hp_max: Optional[int] = None
    new_drivers: Optional[bool] = None
    color: Optional[str] = None
    pollution: Optional[str] = None
    cc_min: Optional[int] = None
    cc_max: Optional[int] = None
    # common
    advertiser: Optional[str] = None
    max_items: int = 300
    enabled: bool = True
    color_hex: Optional[str] = None

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
        # "color" in the JSON means the dashboard colour; the vehicle colour filter is "vehicle_color"
        if "color" in data and str(data["color"]).startswith("#"):
            data["color_hex"] = data.pop("color")
        elif "color" in data:
            data["color"] = data.pop("color")
        if "vehicle_color" in data:
            data["color"] = data.pop("vehicle_color")
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        unknown = set(data) - known
        if unknown:
            log.warning("watch '%s': ignoring unknown keys %s", data["id"], sorted(unknown))
        return cls(**{k: v for k, v in data.items() if k in known})

    # ---------------------------------------------------------------- meta
    @property
    def category_id(self) -> int:
        return category_id(self.category)

    @property
    def domain(self) -> str:
        return domain_of(self.category_id)

    def has_vehicle_filters(self) -> bool:
        return any(getattr(self, f) not in (None, "", False) for f in VEHICLE_FIELDS)

    # ------------------------------------------------------------- params
    def api_params(self, geo: GeoResolver, values: Optional[ValuesResolver] = None) -> Dict[str, Any]:
        cid = self.category_id
        params: Dict[str, Any] = {"c": cid, "t": ad_type_key(self.transaction)}
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

        if self.has_vehicle_filters():
            if cid not in VEHICLE_IDS:
                raise ValueError(f"watch '{self.id}': vehicle filters need category auto, moto, veicoli-commerciali or camper")
            if values is None:
                raise ValueError("vehicle filters need a ValuesResolver")
            self._vehicle_params(params, cid, values)
        return params

    def _vehicle_params(self, params: Dict[str, Any], cid: int, values: ValuesResolver) -> None:
        self._model_query: Optional[str] = None
        if self.brand:
            brand_key, _ = values.brand(cid, self.brand)
            params["cb" if cid == 2 else "bb"] = brand_key
            if self.model:
                model_key = values.model(cid, brand_key, self.model)
                if model_key:
                    params["cm" if cid == 2 else "bm"] = model_key
                else:
                    self._model_query = self.model
        elif self.model:
            self._model_query = self.model
        if self.fuel:
            params["fl"] = values.key("fuel", self.fuel)
        if self.gearbox:
            params["gr"] = values.key("gearbox", self.gearbox)
        if self.body_type:
            params["ct" if cid == 2 else "mt"] = values.key("car_type" if cid == 2 else "motorbike_type", self.body_type)
        if self.vehicle_status:
            params["cvs"] = values.key("vehicle_status", self.vehicle_status)
        if self.color:
            params["cl"] = values.key("color", self.color)
        if self.pollution:
            params["pl"] = values.key("pollution", self.pollution)
        if self.year_min is not None:
            params["ys"] = self.year_min
        if self.year_max is not None:
            params["ye"] = self.year_max
        if self.km_min is not None:
            params["ms"] = values.mileage_key("min", self.km_min)
        if self.km_max is not None:
            params["me"] = values.mileage_key("max", self.km_max)
        if self.hp_min is not None:
            params["hps"] = self.hp_min
        if self.hp_max is not None:
            params["hpe"] = self.hp_max
        if self.new_drivers:
            params["ndo"] = "true"
        if self.cc_min is not None:
            params["ccs"] = self.cc_min
        if self.cc_max is not None:
            params["cce"] = self.cc_max

    def queries(self) -> List[Optional[str]]:
        """Distinct full-text queries to send: one per keyword, an explicit
        ``query``, an unresolved model name, or ``None`` (no text filter)."""
        if self.query:
            return [self.query]
        base: List[str] = []
        model_query = getattr(self, "_model_query", None)
        if self.keywords:
            seen: Set[str] = set()
            for kw in self.keywords:
                norm = normalize_text(kw)
                if norm and norm not in seen:
                    seen.add(norm)
                    base.append(f"{model_query} {kw}" if model_query else kw)
            return base  # type: ignore[return-value]
        if model_query:
            return [model_query]
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
        if not _in_range(record.get("areaSqm"), self.size_min, self.size_max):
            return False
        if not _in_range(record.get("rooms"), self.rooms_min, self.rooms_max):
            return False
        if self.advertiser and record.get("advertType") != ("agency" if ADVERTISER_TYPES[self.advertiser.lower()] else "private"):
            return False
        # vehicles
        if self.brand and record.get("brand") and normalize_text(self.brand) not in normalize_text(record["brand"]):
            return False
        if self.model and record.get("model"):
            wanted = normalize_text(self.model)
            have = normalize_text(" ".join(str(record.get(k) or "") for k in ("model", "modelFull", "version", "title")))
            if wanted not in have:
                return False
        if self.fuel and record.get("fuel") and not _same_choice(self.fuel, record["fuel"]):
            return False
        if self.gearbox and record.get("gearbox") and not _same_choice(self.gearbox, record["gearbox"]):
            return False
        if not _in_range(record.get("year"), self.year_min, self.year_max):
            return False
        if not _in_range(record.get("mileageKm"), self.km_min, self.km_max):
            return False
        if not _in_range(record.get("powerCv"), self.hp_min, self.hp_max):
            return False
        return True

    def summary(self) -> str:
        place = " / ".join(p for p in (self.region, self.province, self.town) if p) or "Italia"
        bits = [self.transaction, self.category, place]
        vehicle = " ".join(p for p in (self.brand, self.model) if p)
        if vehicle:
            bits.append(vehicle)
        for label, v in (("", self.fuel), ("", self.gearbox), ("", self.body_type), ("", self.vehicle_status)):
            if v:
                bits.append(str(v))
        if self.year_min is not None or self.year_max is not None:
            bits.append(f"anno {self.year_min or ''}–{self.year_max or ''}")
        if self.km_max is not None or self.km_min is not None:
            bits.append(f"km {self.km_min or 0}–{self.km_max or '∞'}")
        if self.keywords:
            bits.append("kw: " + ", ".join(self.keywords))
        if self.price_min is not None or self.price_max is not None:
            bits.append(f"€ {self.price_min or 0}–{self.price_max or '∞'}")
        return " · ".join(bits)


# ------------------------------------------------------------------ helpers
def _in_range(value: Optional[int], lo: Optional[int], hi: Optional[int]) -> bool:
    if value is None:
        return True
    if lo is not None and value < lo:
        return False
    if hi is not None and value > hi:
        return False
    return True


def _same_choice(wanted: str, have: str) -> bool:
    w, h = normalize_text(wanted), normalize_text(have)
    aliases = {"gasolio": "diesel", "automatica": "automatico", "automatic": "automatico", "manual": "manuale", "petrol": "benzina"}
    w = aliases.get(w, w)
    return w == h or w in h


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


def run_watch(
    watch: Watch,
    client: SubitoClient,
    geo: GeoResolver,
    store: Store,
    values: Optional[ValuesResolver] = None,
    now: Optional[str] = None,
) -> WatchResult:
    now = now or utcnow()
    result = WatchResult(watch=watch)
    run_id = store.start_run(watch.id)
    seen_ids: Set[str] = set()
    try:
        base_params = watch.api_params(geo, values)
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


def run_all(
    watches: List[Watch],
    client: SubitoClient,
    geo: GeoResolver,
    store: Store,
    values: Optional[ValuesResolver] = None,
) -> Iterator[WatchResult]:
    now = utcnow()
    run_id = store.start_run(None)
    totals = {"fetched": 0, "matched": 0, "new_count": 0, "price_changes": 0}
    for watch in watches:
        if not watch.enabled:
            log.info("[%s] disabled, skipping", watch.id)
            continue
        result = run_watch(watch, client, geo, store, values, now)
        totals["fetched"] += result.fetched
        totals["matched"] += result.matched
        totals["new_count"] += len(result.new)
        totals["price_changes"] += len(result.price_changes)
        yield result
    store.finish_run(run_id, **totals)
    store.commit()
