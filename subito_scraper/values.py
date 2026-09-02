"""Resolve human names to Subito filter keys through ``hades.subito.it/v1/values``.

Vehicle filters (brand, model, fuel, gearbox, mileage bands…) are keyed
lists on the backend. This module fetches those lists once, caches them on
disk and lets a watch say ``"fuel": "diesel"`` or ``"km_max": 120000``."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .api import SubitoClient
from .geo import slugify

log = logging.getLogger(__name__)

VALUES_URL = "https://hades.subito.it/v1/values"

LISTS: Dict[str, str] = {
    "fuel": "fuels/types",
    "gearbox": "gears/types",
    "car_type": "cars/types",
    "motorbike_type": "motorbikes/types",
    "vehicle_type": "vehicles/types",
    "pollution": "pollution/types",
    "vehicle_status": "vehicle_status",
    "color": "colors/types",
    "car_brand": "cars/brands",
    "bike_brand": "motorbikes/brands",
    "mileage_min": "mileage/min",
    "mileage_max": "mileage/max",
}

ALIASES: Dict[str, Dict[str, str]] = {
    "fuel": {"gasolio": "diesel", "petrol": "benzina", "electric": "elettrica", "elettrico": "elettrica", "hybrid": "ibrida", "ibrido": "ibrida", "metano": "metano"},
    "gearbox": {"manual": "manuale", "automatic": "automatico", "automatica": "automatico", "auto": "automatico"},
    "vehicle_status": {"used": "usato", "km 0": "km0", "km-0": "km0", "zero km": "km0", "new": "nuovo"},
    "car_type": {"suv": "suv/fuoristrada", "fuoristrada": "suv/fuoristrada", "sw": "station wagon", "familiare": "station wagon", "city car": "utilitaria", "cabriolet": "cabrio"},
    "motorbike_type": {"enduro": "cross / enduro", "cross": "cross / enduro", "naked": "naked", "custom": "custom / café racer", "cafe racer": "custom / café racer"},
    "vehicle_type": {
        "furgone": "veicoli commerciali fino a 35q", "furgoni": "veicoli commerciali fino a 35q", "van": "veicoli commerciali fino a 35q",
        "commerciali": "veicoli commerciali fino a 35q", "fino a 35q": "veicoli commerciali fino a 35q", "35q": "veicoli commerciali fino a 35q",
        "camion": "veicoli industriali oltre i 35q", "autocarro": "veicoli industriali oltre i 35q", "autocarri": "veicoli industriali oltre i 35q",
        "industriali": "veicoli industriali oltre i 35q", "oltre 35q": "veicoli industriali oltre i 35q", "truck": "veicoli industriali oltre i 35q",
        "trattore": "trattori agricoli", "trattori": "trattori agricoli",
        "agricole": "macchine agricole", "edili": "macchine edili",
    },
}


def _km(value: str) -> int:
    digits = re.sub(r"[^\d]", "", value or "")
    return int(digits) if digits else 0


class ValuesResolver:
    def __init__(self, client: SubitoClient, cache_path: Optional[Path] = None) -> None:
        self.client = client
        self.cache_path = cache_path
        self._cache: Dict[str, List[Dict[str, Any]]] = {}
        if cache_path and cache_path.exists():
            try:
                self._cache = json.loads(cache_path.read_text())
            except ValueError:
                self._cache = {}

    def _save(self) -> None:
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self._cache, ensure_ascii=False))

    def values(self, path: str) -> List[Dict[str, Any]]:
        if path not in self._cache:
            data = self.client.get(f"{VALUES_URL}/{path}")
            self._cache[path] = data.get("values") or []
            self._save()
        return self._cache[path]

    # ------------------------------------------------------------ matching
    @staticmethod
    def _find(values: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
        wanted = slugify(str(name))
        if not wanted:
            return None
        for v in values:
            if slugify(str(v.get("value"))) == wanted or str(v.get("key")) == str(name):
                return v
        starts = [v for v in values if slugify(str(v.get("value"))).startswith(wanted)]
        if len(starts) == 1:
            return starts[0]
        return None

    def key(self, list_name: str, name: Any) -> str:
        """Key for a value in a fixed list (fuel, gearbox, …). Raises with options."""
        path = LISTS[list_name]
        alias = ALIASES.get(list_name, {}).get(str(name).strip().lower())
        found = self._find(self.values(path), alias or name)
        if not found:
            options = ", ".join(str(v.get("value")) for v in self.values(path))
            raise ValueError(f"unknown {list_name} '{name}'. Options: {options}")
        return str(found["key"])

    def brand(self, category_id: int, name: str) -> Tuple[str, str]:
        path = LISTS["car_brand"] if category_id == 2 else LISTS["bike_brand"]
        found = self._find(self.values(path), name)
        if not found:
            raise ValueError(f"unknown brand '{name}' for category {category_id}")
        return str(found["key"]), str(found["value"])

    def model(self, category_id: int, brand_key: str, name: str) -> Optional[str]:
        """Exact model key, or ``None`` when the name is ambiguous (e.g. "Golf"
        spans several generations): the caller then falls back to full-text."""
        path = f"cars/brands/{brand_key}/metamodels" if category_id == 2 else f"motorbikes/brands/{brand_key}/models"
        values = self.values(path)
        wanted = slugify(name)
        exact = [v for v in values if slugify(str(v.get("value"))) == wanted]
        if len(exact) == 1:
            return str(exact[0]["key"])
        partial = [v for v in values if wanted and wanted in slugify(str(v.get("value")))]
        if len(partial) == 1:
            return str(partial[0]["key"])
        if partial:
            log.info("model '%s' matches %d entries (%s); using full-text search instead", name, len(partial), ", ".join(str(v["value"]) for v in partial[:6]))
        else:
            log.warning("model '%s' not found for brand %s; using full-text search", name, brand_key)
        return None

    def mileage_key(self, kind: str, km: int) -> str:
        """Map km to the band key expected by ``ms`` (min) / ``me`` (max)."""
        values = self.values(LISTS["mileage_min" if kind == "min" else "mileage_max"])
        bands = sorted(((_km(v["value"]), str(v["key"])) for v in values if str(v.get("key")) != "0"), key=lambda b: b[0])
        if kind == "min":
            eligible = [b for b in bands if b[0] <= km] or bands[:1]
            return eligible[-1][1]
        eligible = [b for b in bands if b[0] >= km] or bands[-1:]
        return eligible[0][1]
