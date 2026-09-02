"""Turn a raw hades ad into a flat, analysis-ready record.

Field names follow the schema documented by the upstream (closed-source)
Apify actor so exports stay drop-in compatible, plus a few extras."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# category id -> (Italian label, English propertyType, URL slug)
CATEGORIES: Dict[int, tuple] = {
    7: ("Appartamenti", "apartment", "appartamenti"),
    29: ("Ville singole e a schiera", "villa", "ville-singole-e-a-schiera"),
    30: ("Terreni e rustici", "land", "terreni-e-rustici"),
    31: ("Garage e box", "garage", "garage-e-box"),
    32: ("Loft, mansarde e altro", "loft", "loft-mansarde"),
    8: ("Uffici e locali commerciali", "commercial", "uffici-locali-commerciali"),
    43: ("Camere / posti letto", "room", "camere-posti-letto"),
    33: ("Case vacanza", "vacation", "case-vacanza"),
}
CATEGORY_ALIASES: Dict[str, int] = {}
for _cid, (_label, _eng, _slug) in CATEGORIES.items():
    CATEGORY_ALIASES[_eng] = _cid
    CATEGORY_ALIASES[_slug] = _cid
    CATEGORY_ALIASES[str(_cid)] = _cid
CATEGORY_ALIASES.update(
    {
        "apartments": 7,
        "appartamento": 7,
        "case": 7,
        "ville": 29,
        "villas": 29,
        "terreni": 30,
        "garage": 31,
        "box": 31,
        "loft": 32,
        "uffici": 8,
        "offices": 8,
        "camere": 43,
        "rooms": 43,
        "stanze": 43,
        "vacanze": 33,
        "vacation": 33,
        "holiday": 33,
    }
)

AD_TYPES = {"s": "sale", "u": "rent", "k": "wanted"}
AD_TYPE_ALIASES = {
    "sale": "s",
    "vendita": "s",
    "s": "s",
    "rent": "u",
    "affitto": "u",
    "u": "u",
    "wanted": "k",
    "cercasi": "k",
    "k": "k",
}

ADVERTISER_TYPES = {"private": 0, "privato": 0, "agency": 1, "agenzia": 1}

IMAGE_RULE_CARD = "large-fixed-card-2x-auto"
IMAGE_RULE_LARGE = "gallery-desktop-2x-auto"

_INT_RE = re.compile(r"-?\d+")


def category_id(value: Any) -> int:
    key = str(value).strip().lower()
    if key not in CATEGORY_ALIASES:
        raise ValueError(f"unknown category '{value}'. Use one of: {', '.join(sorted(set(CATEGORY_ALIASES)))}")
    return CATEGORY_ALIASES[key]


def ad_type_key(value: Any) -> str:
    key = str(value).strip().lower()
    if key not in AD_TYPE_ALIASES:
        raise ValueError(f"unknown transaction '{value}'. Use sale, rent or wanted")
    return AD_TYPE_ALIASES[key]


def _features(ad: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for feature in ad.get("features") or []:
        values = feature.get("values") or []
        if not values:
            continue
        out[feature.get("uri", "")] = {"type": feature.get("type"), "label": feature.get("label"), **values[0]}
    return out


def _int(value: Any) -> Optional[int]:
    if value is None:
        return None
    match = _INT_RE.search(str(value))
    return int(match.group(0)) if match else None


def _float(value: Any) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _bool(feature: Optional[Dict[str, Any]]) -> Optional[bool]:
    if not feature:
        return None
    key = str(feature.get("key"))
    value = str(feature.get("value", "")).lower()
    if key == "1" or value in ("sì", "si", "yes"):
        return True
    if key in ("0", "2") or value == "no":
        return False
    return None


def _value(feature: Optional[Dict[str, Any]]) -> Optional[str]:
    return feature.get("value") if feature else None


def image_url(image: Dict[str, Any], rule: str = IMAGE_RULE_CARD) -> Optional[str]:
    base = image.get("cdn_base_url") or image.get("cdnBaseUrl") or image.get("base_url")
    if not base:
        return None
    return f"{base}?rule={rule}"


def parse_urn(urn: str) -> tuple:
    """``id:ad:612233839:list:659035166`` -> ("612233839", "659035166")."""
    parts = (urn or "").split(":")
    ad_id = parts[2] if len(parts) > 2 else None
    list_id = parts[4] if len(parts) > 4 else ad_id
    return ad_id, list_id


def normalize(ad: Dict[str, Any], search: Optional[Dict[str, Any]] = None, scraped_at: Optional[str] = None) -> Dict[str, Any]:
    feats = _features(ad)
    geo = ad.get("geo") or {}
    region = geo.get("region") or {}
    city = geo.get("city") or {}
    town = geo.get("town") or {}
    zone = geo.get("zone") or {}
    gmap = geo.get("map") or {}
    advertiser = ad.get("advertiser") or {}
    images = ad.get("images") or []
    category = ad.get("category") or {}
    ad_type = (ad.get("type") or {}).get("key")
    dates = ad.get("dates") or {}

    ad_id, list_id = parse_urn(ad.get("urn", ""))
    price = _int((feats.get("/price") or {}).get("key"))
    area = _int((feats.get("/size") or {}).get("key"))
    terrain = _int((feats.get("/terrain_size") or {}).get("key"))
    price_per_sqm = round(price / area) if price and area else None

    cat_id = _int(category.get("key"))
    cat_meta = CATEGORIES.get(cat_id or -1)
    body = (ad.get("body") or "").strip()

    # NB: the "/nosalesman" feature is NOT an agency marker (private ads carry it too); trust advertiser.company
    is_company = advertiser.get("company") is True
    lat = _float(gmap.get("latitude")) or _float(town.get("lat"))
    lon = _float(gmap.get("longitude")) or _float(town.get("lon"))

    parking = _value(feats.get("/parking"))
    address_parts = [p for p in (zone.get("value"), town.get("value")) if p]
    full_address = ", ".join(address_parts)
    if city.get("short_name"):
        full_address = f"{full_address} ({city['short_name']})" if full_address else city.get("value", "")

    record: Dict[str, Any] = {
        "adId": list_id,
        "urn": ad.get("urn"),
        "detailUrl": (ad.get("urls") or {}).get("default"),
        "title": (ad.get("subject") or "").strip(),
        "shortDescription": body[:220] + ("…" if len(body) > 220 else ""),
        "description": body,
        "transactionType": AD_TYPES.get(ad_type, ad_type),
        "propertyType": cat_meta[1] if cat_meta else category.get("friendly_name"),
        "categoryId": cat_id,
        "categoryLabel": category.get("value"),
        "advertType": "agency" if is_company else "private",
        "price": price,
        "priceCurrency": "EUR" if price is not None else None,
        "pricePerSqm": price_per_sqm,
        "areaSqm": area,
        "terrainAreaSqm": terrain,
        "rooms": _int((feats.get("/room") or {}).get("value")),
        "roomsLabel": _value(feats.get("/room")),
        "bathrooms": _int((feats.get("/bathrooms") or {}).get("value")),
        "floor": _value(feats.get("/floor")),
        "buildingCondition": _value(feats.get("/building_condition")),
        "heatingType": _value(feats.get("/heating")),
        "energyClass": _value(feats.get("/energy_class")),
        "hasElevator": _bool(feats.get("/elevator")),
        "hasParking": (parking is not None and parking.lower() not in ("no", "nessuno")) if parking is not None else None,
        "parkingType": parking,
        "hasBalcony": _bool(feats.get("/balcony")),
        "hasGarden": _bool(feats.get("/garden")),
        "hasAirConditioning": _bool(feats.get("/air_conditioning")),
        "isFurnished": _bool(feats.get("/furnished")),
        "isLastFloor": _bool(feats.get("/last_floor")),
        "isMultiLevel": _bool(feats.get("/multi_level")),
        "hasReception": _bool(feats.get("/reception")),
        "isAvailableNow": _bool(feats.get("/available_now")),
        "isShortRental": _bool(feats.get("/is_rental")),
        "roomType": _value(feats.get("/room_type")),
        "country": "Italia",
        "region": region.get("value"),
        "regionId": _int(region.get("key")),
        "province": city.get("value"),
        "provinceId": _int(city.get("key")),
        "provinceCode": city.get("short_name"),
        "city": town.get("value"),
        "cityIstat": town.get("istat"),
        "microLocation": zone.get("value"),
        "fullAddress": full_address,
        "latitude": lat,
        "longitude": lon,
        "mainImageUrl": image_url(images[0]) if images else None,
        "imageUrls": [u for u in (image_url(i, IMAGE_RULE_LARGE) for i in images) if u],
        "imageCount": len(images),
        "advertiserId": advertiser.get("user_id"),
        "advertiserName": advertiser.get("shop_name") or advertiser.get("name"),
        "advertiserType": "agency" if is_company else "private",
        "advertiserShopId": advertiser.get("shop_id"),
        "datePosted": dates.get("display_iso8601") or dates.get("display"),
        "dateExpiration": dates.get("expiration_iso8601"),
        "scrapedAt": scraped_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    if search:
        record["searchRegion"] = search.get("region")
        record["searchProvince"] = search.get("province")
        record["searchTown"] = search.get("town")
        record["searchKeyword"] = search.get("query")
        record["searchWatch"] = search.get("watch")
    return record


def record_text(record: Dict[str, Any]) -> str:
    """Text used for keyword matching (title + description + place)."""
    return " ".join(
        str(record.get(k) or "")
        for k in ("title", "description", "city", "microLocation", "province", "advertiserName")
    )


def to_rows(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten list fields for CSV/XLSX export."""
    rows = []
    for rec in records:
        row = dict(rec)
        row["imageUrls"] = " ".join(rec.get("imageUrls") or [])
        rows.append(row)
    return rows
