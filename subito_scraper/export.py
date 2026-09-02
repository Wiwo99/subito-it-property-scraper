"""Export normalized records to CSV / JSON / JSONL / XLSX."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from .models import to_rows

FORMATS = ("csv", "json", "jsonl", "xlsx")


def export(records: List[Dict[str, Any]], path: Path, fmt: str = "") -> Path:
    path = Path(path)
    fmt = (fmt or path.suffix.lstrip(".") or "json").lower()
    if fmt not in FORMATS:
        raise ValueError(f"unsupported format '{fmt}', choose from {FORMATS}")
    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        path.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    elif fmt == "jsonl":
        with path.open("w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    elif fmt == "csv":
        rows = to_rows(records)
        fields = _fieldnames(rows)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    elif fmt == "xlsx":
        try:
            from openpyxl import Workbook
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("xlsx export needs openpyxl: pip install 'subito-scraper[xlsx]'") from exc
        rows = to_rows(records)
        fields = _fieldnames(rows)
        wb = Workbook()
        ws = wb.active
        ws.title = "listings"
        ws.append(fields)
        for row in rows:
            ws.append([_cell(row.get(f)) for f in fields])
        wb.save(str(path))
    return path


def _fieldnames(rows: List[Dict[str, Any]]) -> List[str]:
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    return fields


def _cell(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value
