"""Build the static dashboard: one self-contained HTML file with the data
embedded, so it works from ``file://``, GitHub Pages or any static host
without a server process."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .store import Store
from .watches import Watch

TEMPLATE = Path(__file__).resolve().parent.parent / "dashboard" / "template.html"
PLACEHOLDER = "/*__DASHBOARD_DATA__*/"

COMMON_FIELDS = (
    "adId", "detailUrl", "title", "shortDescription", "domain", "transactionType", "propertyType", "categoryLabel",
    "advertType", "advertiserName", "price", "region", "province", "provinceCode", "city", "microLocation",
    "latitude", "longitude", "mainImageUrl", "imageUrls", "imageCount", "datePosted", "firstSeen", "lastSeen", "isUrgent",
)
REALESTATE_FIELDS = (
    "pricePerSqm", "areaSqm", "rooms", "bathrooms", "floor", "buildingCondition", "heatingType", "energyClass",
    "hasElevator", "hasParking", "hasBalcony", "hasGarden", "hasAirConditioning", "isFurnished",
)
MOTORI_FIELDS = (
    "brand", "model", "modelFull", "version", "year", "registerDate", "mileageKm", "fuel", "gearbox", "bodyType", "doors",
    "seats", "color", "pollution", "powerKw", "powerCv", "vehicleStatus", "forNewDrivers", "vatDeductible",
    "warrantyMonths", "itemCondition", "shipLength",
)


def build_payload(store: Store, watches: List[Watch], new_window_hours: int = 36, include_orphans: bool = False) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    matches = store.matches_by_listing()
    history = store.price_history()
    previous_run = store.previous_run_started()
    new_cutoff = (now - timedelta(hours=new_window_hours)).isoformat(timespec="seconds")
    # "new" = first seen after the previous full run (or within the window when there is no history)
    new_since = max(previous_run or "", new_cutoff) if previous_run else new_cutoff
    active_ids = {w.id for w in watches if w.enabled}

    listings: List[Dict[str, Any]] = []
    for rec in store.listings():
        ad_id = rec["adId"]
        watch_ids = [m["watchId"] for m in matches.get(ad_id, []) if m["watchId"] in active_ids]
        if not watch_ids and not include_orphans:
            continue
        fields = COMMON_FIELDS + (MOTORI_FIELDS if rec.get("domain") == "motori" else REALESTATE_FIELDS)
        compact = {k: rec.get(k) for k in fields if rec.get(k) is not None}
        compact.setdefault("domain", "realestate")
        compact["adId"] = ad_id
        compact["imageUrls"] = (rec.get("imageUrls") or [])[:6]
        compact["watches"] = watch_ids
        compact["isNew"] = (rec.get("firstSeen") or "") >= new_since
        hist = history.get(ad_id) or []
        if len(hist) >= 2 and hist[-1]["price"] is not None and hist[-2]["price"] is not None:
            compact["previousPrice"] = hist[-2]["price"]
            compact["priceDelta"] = hist[-1]["price"] - hist[-2]["price"]
        else:
            compact["previousPrice"] = None
            compact["priceDelta"] = 0
        compact["priceHistory"] = [h["price"] for h in hist][-8:]
        listings.append(compact)

    watch_payload = []
    for w in watches:
        if not w.enabled:
            continue
        ids = [l for l in listings if w.id in l["watches"]]
        watch_payload.append(
            {
                "id": w.id,
                "name": w.name,
                "summary": w.summary(),
                "domain": w.domain,
                "keywords": w.keywords,
                "exclude": w.exclude,
                "color": w.color_hex,
                "count": len(ids),
                "newCount": sum(1 for l in ids if l["isNew"]),
            }
        )

    return {
        "generatedAt": now.isoformat(timespec="seconds"),
        "newSince": new_since,
        "counts": {**store.counts(), "shown": len(listings), "new": sum(1 for l in listings if l["isNew"])},
        "watches": watch_payload,
        "listings": listings,
        "runs": store.last_runs(30),
    }


def render(payload: Dict[str, Any], template_path: Optional[Path] = None) -> str:
    template = (template_path or TEMPLATE).read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise ValueError(f"template is missing the {PLACEHOLDER} placeholder")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/")  # never terminate the script tag early
    return template.replace(PLACEHOLDER, "window.__DASHBOARD_DATA__ = " + data + ";")


def build(
    store: Store,
    watches: List[Watch],
    out: Path,
    template_path: Optional[Path] = None,
    write_json: bool = True,
    include_orphans: bool = False,
) -> Path:
    payload = build_payload(store, watches, include_orphans=include_orphans)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(payload, template_path), encoding="utf-8")
    if write_json:
        (out.parent / "data.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return out
