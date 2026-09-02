"""Geography helpers.

Region ids are static; provinces and towns are resolved through Subito's
public geo API (``hades.subito.it/v1/geo``) and cached on disk, so a watch
can simply say ``"province": "bergamo", "town": "treviglio"``."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

from .api import SubitoClient, SubitoNotFound

log = logging.getLogger(__name__)

GEO_URL = "https://hades.subito.it/v1/geo"

# slug -> (id, display name). Ids verified against ``/v1/geo/regions``.
REGIONS: Dict[str, tuple] = {
    "valle-d-aosta": (1, "Valle d'Aosta"),
    "piemonte": (2, "Piemonte"),
    "liguria": (3, "Liguria"),
    "lombardia": (4, "Lombardia"),
    "trentino-alto-adige": (5, "Trentino-Alto Adige"),
    "veneto": (6, "Veneto"),
    "friuli-venezia-giulia": (7, "Friuli-Venezia Giulia"),
    "emilia-romagna": (8, "Emilia-Romagna"),
    "toscana": (9, "Toscana"),
    "umbria": (10, "Umbria"),
    "lazio": (11, "Lazio"),
    "marche": (12, "Marche"),
    "abruzzo": (13, "Abruzzo"),
    "molise": (14, "Molise"),
    "campania": (15, "Campania"),
    "puglia": (16, "Puglia"),
    "basilicata": (17, "Basilicata"),
    "calabria": (18, "Calabria"),
    "sardegna": (19, "Sardegna"),
    "sicilia": (20, "Sicilia"),
}


def slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()


def region_id(region: Optional[str]) -> Optional[int]:
    if not region or slugify(region) in ("italia", "italy", "tutta-italia"):
        return None
    slug = slugify(region)
    if slug not in REGIONS:
        raise ValueError(f"unknown region '{region}'. Valid slugs: {', '.join(REGIONS)}")
    return REGIONS[slug][0]


def _same(a: Optional[str], b: Optional[str]) -> bool:
    return slugify(a or "") == slugify(b or "")


class GeoResolver:
    """Resolve ``(region, province, town)`` to hades params ``r``, ``ci``, ``to``."""

    def __init__(self, client: SubitoClient, cache_path: Optional[Path] = None) -> None:
        self.client = client
        self.cache_path = cache_path
        self._cache: Dict[str, Any] = {"resolved": {}, "cities": {}, "towns": {}}
        if cache_path and cache_path.exists():
            try:
                loaded = json.loads(cache_path.read_text())
                if isinstance(loaded, dict) and "resolved" in loaded:
                    self._cache.update(loaded)
            except ValueError:
                pass

    def _save(self) -> None:
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self._cache, indent=1, ensure_ascii=False))

    # ----------------------------------------------------------- raw lists
    def cities(self, rid: int) -> List[Dict[str, Any]]:
        key = str(rid)
        if key not in self._cache["cities"]:
            data = self.client.get(f"{GEO_URL}/regions/{rid}/cities")
            self._cache["cities"][key] = data.get("values") or []
            self._save()
        return self._cache["cities"][key]

    def towns(self, rid: int, city_id: int) -> List[Dict[str, Any]]:
        key = f"{rid}/{city_id}"
        if key not in self._cache["towns"]:
            data = self.client.get(f"{GEO_URL}/regions/{rid}/cities/{city_id}/towns")
            self._cache["towns"][key] = data.get("values") or []
            self._save()
        return self._cache["towns"][key]

    # -------------------------------------------------------------- resolve
    def resolve(self, region: Optional[str], province: Optional[str] = None, town: Optional[str] = None) -> Dict[str, Any]:
        rid = region_id(region)
        result: Dict[str, Any] = {"r": rid}
        if rid is None:
            if province or town:
                raise ValueError("province/town need a region, e.g. region=lombardia province=bergamo")
            return result
        if not (province or town):
            return result

        key = "/".join(slugify(x) for x in (region or "", province or "", town or ""))
        if key in self._cache["resolved"]:
            return dict(self._cache["resolved"][key])

        city: Optional[Dict[str, Any]] = None
        if province:
            city = next(
                (c for c in self.cities(rid) if _same(c.get("friendly_name"), province) or _same(c.get("value"), province) or _same(c.get("short_name"), province)),
                None,
            )
            if not city:
                names = ", ".join(c.get("friendly_name", "") for c in self.cities(rid))
                raise ValueError(f"unknown province '{province}' in {region}. Options: {names}")
            result["ci"] = int(city["key"])
            result["province_name"] = city.get("value")
            result["province_code"] = city.get("short_name")

        if town:
            candidates = [city] if city else self.cities(rid)
            found = None
            for c in candidates:
                try:
                    towns = self.towns(rid, int(c["key"]))
                except SubitoNotFound:
                    continue
                found = next((t for t in towns if _same(t.get("friendly_name"), town) or _same(t.get("value"), town)), None)
                if found:
                    if not city:
                        result["ci"] = int(c["key"])
                        result["province_name"] = c.get("value")
                        result["province_code"] = c.get("short_name")
                    break
            if not found:
                where = f"{region}/{province}" if province else region
                raise ValueError(f"unknown town '{town}' in {where}")
            result["to"] = found["istat"]
            result["town_name"] = found.get("value")

        self._cache["resolved"][key] = result
        self._save()
        return dict(result)
