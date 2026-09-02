"""Thin client for Subito.it's public search backend (hades).

The website itself calls ``https://hades.subito.it/v1/search/items`` from the
browser, so no login or API key is required. This module only adds what a
polite, resilient client needs: a browser-like User-Agent, a fixed delay
between requests, retries with exponential backoff on transient errors and
transparent pagination.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, Iterator, Optional

import requests

log = logging.getLogger(__name__)

SEARCH_URL = "https://hades.subito.it/v1/search/items"
SITE_URL = "https://www.subito.it"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
]

MAX_PAGE_SIZE = 100


class SubitoError(RuntimeError):
    """Raised when the backend keeps failing after all retries."""


class SubitoNotFound(SubitoError):
    """Raised on 404 (unknown place)."""


class SubitoBlocked(SubitoError):
    """Raised on other 4xx responses (bad parameters, 403 from the edge)."""


HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Origin": None,  # requests drops headers set to None
    "Referer": SITE_URL + "/",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}


class SubitoClient:
    def __init__(
        self,
        delay: float = 0.7,
        timeout: float = 20.0,
        retries: int = 4,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
                "Origin": SITE_URL,
                "Referer": SITE_URL + "/",
            }
        )
        self._last_request = 0.0
        self.requests_made = 0

    # ------------------------------------------------------------------ http
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request = time.monotonic()

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, json: bool = True) -> Any:
        """GET with throttling and retries. Returns parsed JSON or response text.

        HTML pages get browser-like headers: the JSON ``Accept``/``Origin`` pair
        used for hades is rejected with 403 by the website's edge."""
        headers = None if json else HTML_HEADERS
        last_exc: Optional[BaseException] = None
        for attempt in range(self.retries + 1):
            self._throttle()
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout, headers=headers)
                self.requests_made += 1
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise SubitoError(f"HTTP {resp.status_code} from {resp.url}")
                if resp.status_code == 404:
                    raise SubitoNotFound(f"HTTP 404 from {resp.url}")
                if 400 <= resp.status_code < 500:
                    # other client errors (400 bad params, 403 blocked) will not heal by retrying
                    raise SubitoBlocked(f"HTTP {resp.status_code} from {resp.url}")
                resp.raise_for_status()
                return resp.json() if json else resp.text
            except (SubitoNotFound, SubitoBlocked):
                raise
            except (requests.RequestException, SubitoError, ValueError) as exc:
                last_exc = exc
                if attempt == self.retries:
                    break
                wait = min(30.0, (2**attempt) * 1.5 + random.uniform(0, 0.8))
                log.warning("request failed (%s), retry %d/%d in %.1fs", exc, attempt + 1, self.retries, wait)
                time.sleep(wait)
        raise SubitoError(f"giving up on {url}: {last_exc}")

    # --------------------------------------------------------------- search
    def search_page(self, params: Dict[str, Any], start: int = 0, limit: int = MAX_PAGE_SIZE) -> Dict[str, Any]:
        query = {"qso": "false", "shp": "false", "urg": "false", "sort": "datedesc"}
        query.update({k: v for k, v in params.items() if v not in (None, "", [])})
        query["start"] = start
        query["lim"] = min(limit, MAX_PAGE_SIZE)
        return self.get(SEARCH_URL, query)

    def iter_ads(self, params: Dict[str, Any], max_items: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        """Yield raw ad dicts, paginating until ``count_all`` or ``max_items``."""
        start = 0
        yielded = 0
        total: Optional[int] = None
        while True:
            page_size = MAX_PAGE_SIZE if max_items is None else min(MAX_PAGE_SIZE, max_items - yielded)
            if page_size <= 0:
                return
            data = self.search_page(params, start=start, limit=page_size)
            ads = data.get("ads") or []
            if total is None:
                total = int(data.get("count_all") or 0)
                log.info("search matches %d listings", total)
            for ad in ads:
                yield ad
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return
            start += len(ads)
            if not ads or start >= total:
                return

    def count(self, params: Dict[str, Any]) -> int:
        return int(self.search_page(params, start=0, limit=1).get("count_all") or 0)
