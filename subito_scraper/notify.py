"""Optional alerts for new matches: Telegram bot and generic JSON webhook.

Configure through environment variables so secrets never live in the repo:

* ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID``
* ``NOTIFY_WEBHOOK_URL`` (POST, JSON body)
"""

from __future__ import annotations

import html
import json
import logging
import os
from typing import Any, Dict, List

import requests

from .watches import WatchResult

log = logging.getLogger(__name__)

MAX_PER_MESSAGE = 8


def _fmt_price(value: Any) -> str:
    return f"{value:,.0f} €".replace(",", ".") if isinstance(value, (int, float)) else "n.d."


def _line(rec: Dict[str, Any]) -> str:
    bits = [_fmt_price(rec.get("price"))]
    if rec.get("areaSqm"):
        bits.append(f"{rec['areaSqm']} mq")
    if rec.get("pricePerSqm"):
        bits.append(f"{rec['pricePerSqm']} €/mq")
    if rec.get("rooms"):
        bits.append(f"{rec['rooms']} loc.")
    place = rec.get("fullAddress") or rec.get("city") or ""
    title = html.escape(rec.get("title") or "annuncio")
    url = rec.get("detailUrl") or ""
    return f"• <a href=\"{url}\">{title}</a>\n   {' · '.join(bits)} — {html.escape(place)}"


def telegram_messages(results: List[WatchResult]) -> List[str]:
    messages: List[str] = []
    for res in results:
        if not res.new and not res.price_changes:
            continue
        head = f"<b>🏠 {html.escape(res.watch.name)}</b>"
        if res.new:
            chunk = [head, f"{len(res.new)} nuovi annunci"]
            for rec in res.new[:MAX_PER_MESSAGE]:
                chunk.append(_line(rec))
            if len(res.new) > MAX_PER_MESSAGE:
                chunk.append(f"… e altri {len(res.new) - MAX_PER_MESSAGE}")
            messages.append("\n".join(chunk))
        if res.price_changes:
            chunk = [head, f"{len(res.price_changes)} variazioni di prezzo"]
            for rec in res.price_changes[:MAX_PER_MESSAGE]:
                chunk.append(_line(rec) + f"\n   era {_fmt_price(rec.get('previousPrice'))}")
            messages.append("\n".join(chunk))
    return messages


def send_telegram(results: List[WatchResult]) -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log.info("telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID), skipping")
        return 0
    sent = 0
    for text in telegram_messages(results):
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=20,
        )
        if resp.ok:
            sent += 1
        else:
            log.error("telegram error %s: %s", resp.status_code, resp.text[:200])
    return sent


def send_webhook(results: List[WatchResult]) -> bool:
    url = os.environ.get("NOTIFY_WEBHOOK_URL")
    if not url:
        return False
    payload = [
        {
            "watch": {"id": r.watch.id, "name": r.watch.name},
            "new": r.new,
            "priceChanges": r.price_changes,
            "fetched": r.fetched,
            "matched": r.matched,
            "error": r.error,
        }
        for r in results
        if r.new or r.price_changes or r.error
    ]
    if not payload:
        return False
    resp = requests.post(url, data=json.dumps(payload, ensure_ascii=False), headers={"Content-Type": "application/json"}, timeout=20)
    if not resp.ok:
        log.error("webhook error %s: %s", resp.status_code, resp.text[:200])
    return resp.ok


def notify(results: List[WatchResult]) -> Dict[str, Any]:
    return {"telegram": send_telegram(results), "webhook": send_webhook(results)}
