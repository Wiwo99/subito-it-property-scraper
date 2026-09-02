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

COMPACT_FIELDS = (
    "adId",
    "detailUrl",
    "title",
    "shortDescription",
    "transactionType",
    "propertyType",
    "categoryLabel",
    "advertType",
    "advertiserName",
    "price",
    "pricePerSqm",
    "areaSqm",
    "rooms",
    "bathrooms",
    "floor",
    "buildingCondition",
    "heatingType",
    "energyClass",
    "hasElevator",
    "hasParking",
    "hasBalcony",
    "hasGarden",
    "hasAirConditioning",
    "isFurnished",
    "region",
    "province",
    "provinceCode",
    "city",
    "microLocation",
    "latitude",
    "longitude",
    "mainImageUrl",
    "imageUrls",
    "imageCount",
    "datePosted",
    "firstSeen",
    "lastSeen",
)


def build_payload(store: Store, watches: List[Watch], new_window_hours: int = 36) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    matches = store.matches_by_listing()
    history = store.price_history()
    previous_run = store.previous_run_started()
    new_cutoff = (now - timedelta(hours=new_window_hours)).isoformat(timespec="seconds")
    # "new" = first seen after the previous full run (or within the window when there is no history)
    new_since = max(previous_run or "", new_cutoff) if previous_run else new_cutoff

    listings: List[Dict[str, Any]] = []
    for rec in store.listings():
        ad_id = rec["adId"]
        compact = {k: rec.get(k) for k in COMPACT_FIELDS}
        compact["imageUrls"] = (rec.get("imageUrls") or [])[:6]
        compact["watches"] = [m["watchId"] for m in matches.get(ad_id, [])]
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
        ids = [l for l in listings if w.id in l["watches"]]
        watch_payload.append(
            {
                "id": w.id,
                "name": w.name,
                "summary": w.summary(),
                "enabled": w.enabled,
                "keywords": w.keywords,
                "exclude": w.exclude,
                "color": w.color,
                "count": len(ids),
                "newCount": sum(1 for l in ids if l["isNew"]),
            }
        )

    runs = store.last_runs(30)
    return {
        "generatedAt": now.isoformat(timespec="seconds"),
        "newSince": new_since,
        "counts": {**store.counts(), "new": sum(1 for l in listings if l["isNew"])},
        "watches": watch_payload,
        "listings": listings,
        "runs": runs,
    }


def render(payload: Dict[str, Any], template_path: Optional[Path] = None) -> str:
    template = (template_path or TEMPLATE).read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise ValueError(f"template is missing the {PLACEHOLDER} placeholder")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/")  # never terminate the script tag early
    return template.replace(PLACEHOLDER, "window.__DASHBOARD_DATA__ = " + data + ";")


def build(store: Store, watches: List[Watch], out: Path, template_path: Optional[Path] = None, write_json: bool = True) -> Path:
    payload = build_payload(store, watches)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(payload, template_path), encoding="utf-8")
    if write_json:
        (out.parent / "data.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return out
