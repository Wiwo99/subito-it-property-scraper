"""SQLite persistence: listings, price history, watch matches and runs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    ad_id TEXT PRIMARY KEY,
    urn TEXT,
    title TEXT,
    price INTEGER,
    area_sqm INTEGER,
    price_per_sqm INTEGER,
    transaction_type TEXT,
    property_type TEXT,
    advert_type TEXT,
    region TEXT,
    province TEXT,
    city TEXT,
    date_posted TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_listings_last_seen ON listings(last_seen);
CREATE INDEX IF NOT EXISTS idx_listings_first_seen ON listings(first_seen);

CREATE TABLE IF NOT EXISTS price_history (
    ad_id TEXT NOT NULL,
    price INTEGER,
    seen_at TEXT NOT NULL,
    PRIMARY KEY (ad_id, seen_at)
);

CREATE TABLE IF NOT EXISTS watch_matches (
    watch_id TEXT NOT NULL,
    ad_id TEXT NOT NULL,
    first_matched TEXT NOT NULL,
    last_matched TEXT NOT NULL,
    PRIMARY KEY (watch_id, ad_id)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    fetched INTEGER DEFAULT 0,
    matched INTEGER DEFAULT 0,
    new_count INTEGER DEFAULT 0,
    price_changes INTEGER DEFAULT 0,
    error TEXT
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.conn.commit()
        self.close()

    # ------------------------------------------------------------- listings
    def upsert_listing(self, record: Dict[str, Any], now: Optional[str] = None) -> Tuple[str, Optional[int]]:
        """Insert or refresh a listing.

        Returns ``(status, previous_price)`` where status is ``new``,
        ``price_changed`` or ``seen``."""
        now = now or utcnow()
        ad_id = record["adId"]
        row = self.conn.execute("SELECT price, first_seen FROM listings WHERE ad_id = ?", (ad_id,)).fetchone()
        payload = json.dumps(record, ensure_ascii=False)
        cols = (
            record.get("urn"),
            record.get("title"),
            record.get("price"),
            record.get("areaSqm"),
            record.get("pricePerSqm"),
            record.get("transactionType"),
            record.get("propertyType"),
            record.get("advertType"),
            record.get("region"),
            record.get("province"),
            record.get("city"),
            record.get("datePosted"),
        )
        if row is None:
            self.conn.execute(
                """INSERT INTO listings (ad_id, urn, title, price, area_sqm, price_per_sqm, transaction_type,
                   property_type, advert_type, region, province, city, date_posted, first_seen, last_seen, data)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ad_id, *cols, now, now, payload),
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO price_history (ad_id, price, seen_at) VALUES (?,?,?)",
                (ad_id, record.get("price"), now),
            )
            return "new", None

        previous_price = row["price"]
        self.conn.execute(
            """UPDATE listings SET urn=?, title=?, price=?, area_sqm=?, price_per_sqm=?, transaction_type=?,
               property_type=?, advert_type=?, region=?, province=?, city=?, date_posted=?, last_seen=?, data=?
               WHERE ad_id=?""",
            (*cols, now, payload, ad_id),
        )
        if previous_price != record.get("price"):
            self.conn.execute(
                "INSERT OR REPLACE INTO price_history (ad_id, price, seen_at) VALUES (?,?,?)",
                (ad_id, record.get("price"), now),
            )
            return "price_changed", previous_price
        return "seen", previous_price

    def record_match(self, watch_id: str, ad_id: str, now: Optional[str] = None) -> bool:
        """Link a listing to a watch. Returns True when the match is new."""
        now = now or utcnow()
        cur = self.conn.execute(
            "UPDATE watch_matches SET last_matched=? WHERE watch_id=? AND ad_id=?", (now, watch_id, ad_id)
        )
        if cur.rowcount:
            return False
        self.conn.execute(
            "INSERT INTO watch_matches (watch_id, ad_id, first_matched, last_matched) VALUES (?,?,?,?)",
            (watch_id, ad_id, now, now),
        )
        return True

    def start_run(self, watch_id: Optional[str]) -> int:
        cur = self.conn.execute("INSERT INTO runs (watch_id, started_at) VALUES (?, ?)", (watch_id, utcnow()))
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, **stats: Any) -> None:
        allowed = {"fetched", "matched", "new_count", "price_changes", "error"}
        fields = {k: v for k, v in stats.items() if k in allowed}
        fields["finished_at"] = utcnow()
        sets = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE runs SET {sets} WHERE id=?", (*fields.values(), run_id))

    def commit(self) -> None:
        self.conn.commit()

    # -------------------------------------------------------------- queries
    def listings(self, watch_id: Optional[str] = None, since: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT l.data, l.first_seen, l.last_seen FROM listings l"
        args: List[Any] = []
        where = []
        if watch_id:
            sql += " JOIN watch_matches m ON m.ad_id = l.ad_id AND m.watch_id = ?"
            args.append(watch_id)
        if since:
            where.append("l.first_seen >= ?")
            args.append(since)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY l.date_posted DESC"
        out = []
        for row in self.conn.execute(sql, args):
            rec = json.loads(row["data"])
            rec["firstSeen"] = row["first_seen"]
            rec["lastSeen"] = row["last_seen"]
            out.append(rec)
        return out

    def matches_by_listing(self) -> Dict[str, List[Dict[str, str]]]:
        out: Dict[str, List[Dict[str, str]]] = {}
        for row in self.conn.execute("SELECT watch_id, ad_id, first_matched, last_matched FROM watch_matches"):
            out.setdefault(row["ad_id"], []).append(
                {"watchId": row["watch_id"], "firstMatched": row["first_matched"], "lastMatched": row["last_matched"]}
            )
        return out

    def price_history(self) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        for row in self.conn.execute("SELECT ad_id, price, seen_at FROM price_history ORDER BY seen_at"):
            out.setdefault(row["ad_id"], []).append({"price": row["price"], "at": row["seen_at"]})
        return out

    def last_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def last_run_started(self) -> Optional[str]:
        row = self.conn.execute("SELECT MAX(started_at) AS s FROM runs WHERE watch_id IS NULL").fetchone()
        return row["s"] if row else None

    def previous_run_started(self) -> Optional[str]:
        rows = self.conn.execute(
            "SELECT started_at FROM runs WHERE watch_id IS NULL ORDER BY id DESC LIMIT 2"
        ).fetchall()
        return rows[1]["started_at"] if len(rows) > 1 else None

    def counts(self) -> Dict[str, int]:
        total = self.conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        matches = self.conn.execute("SELECT COUNT(*) FROM watch_matches").fetchone()[0]
        return {"listings": total, "matches": matches}

    def prune(self, older_than_iso: str) -> int:
        """Delete listings not seen since ``older_than_iso``. Returns rows removed."""
        ids = [r[0] for r in self.conn.execute("SELECT ad_id FROM listings WHERE last_seen < ?", (older_than_iso,))]
        if not ids:
            return 0
        self._delete_ids("listings", ids)
        self._delete_ids("price_history", ids)
        self._delete_ids("watch_matches", ids)
        return len(ids)

    def _delete_ids(self, table: str, ids: Iterable[str]) -> None:
        ids = list(ids)
        for i in range(0, len(ids), 500):
            chunk = ids[i : i + 500]
            marks = ",".join("?" * len(chunk))
            self.conn.execute(f"DELETE FROM {table} WHERE ad_id IN ({marks})", chunk)
