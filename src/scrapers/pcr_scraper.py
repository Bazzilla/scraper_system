"""Equity Put/Call Ratio scraper module.

Fetches the CBOE daily market statistics page and extracts the EQUITY PUT/CALL
RATIO (plus total and index ratios for context). The page embeds the data as an
escaped JSON string in a Next.js ``__next_f`` payload, which is de-escaped and
parsed. Returns a dict in the file.json output format.

NOTE: the strategy originally targeted Barchart, but Barchart is not scrapable
(WAF 404). CBOE is the official primary source of the data Barchart aggregates.

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

CBOE_DAILY_URL = "https://www.cboe.com/us/options/market_statistics/daily/"

DEFAULT_TIMEOUT = 20
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 2.0
DEFAULT_STALE_AFTER_HOURS = 24
FREQUENCY = "daily"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def parse_ratios(html: str) -> dict[str, Any]:
    """Extract put/call ratios from the CBOE daily market statistics page.

    The data lives in an escaped JSON string inside a ``__next_f`` push.
    Returns a dict with equity_pcr, total_pcr, index_pcr and trade_date.

    Raises:
        ValueError: If the ratios block cannot be found or parsed.
    """
    # Primary: extract the escaped ratios array. The array ends right before
    # the next field ("SUM OF ALL PRODUCTS") — stopping at `]}` would swallow
    # that following data and break the JSON parse.
    m = re.search(r'\\"ratios\\":\[(.*?)\],\\"SUM OF ALL PRODUCTS', html, re.S)
    if m:
        try:
            clean = m.group(1).replace('\\"', '"').replace('\\\\', '')
            rows = json.loads(f"[{clean}]")
        except ValueError:
            logger.warning("CBOE ratios block matched but failed to parse")
            rows = None
    else:
        rows = None

    if rows is None:
        # Fallback: direct regex on the escaped equity entry.
        m2 = re.search(r'\\"EQUITY PUT/CALL RATIO\\",\\"value\\":\\"([\d.]+)\\"', html)
        if not m2:
            raise ValueError("CBOE page does not contain put/call ratio data")
        logger.warning("Using equity-only fallback (ratios block not parsed)")
        rows = [{"name": "EQUITY PUT/CALL RATIO", "value": m2.group(1)}]

    def _ratio(name: str) -> float | None:
        for row in rows:
            if row.get("name") == name:
                try:
                    return float(row["value"])
                except (KeyError, TypeError, ValueError):
                    return None
        return None

    trade_date: str | None = None
    m_date = re.search(r'\\"selectedDate\\":\\"(\d{4}-\d{2}-\d{2})\\"', html)
    if m_date:
        trade_date = m_date.group(1)

    return {
        "equity_pcr": _ratio("EQUITY PUT/CALL RATIO"),
        "total_pcr": _ratio("TOTAL PUT/CALL RATIO"),
        "index_pcr": _ratio("INDEX PUT/CALL RATIO"),
        "trade_date": trade_date,
    }


def build_result(
    data: dict[str, Any],
    fetched_at: str | None = None,
    stale_after_hours: int = DEFAULT_STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Build the output dict in the file.json format."""
    return {
        "equity_pcr": data.get("equity_pcr"),
        "total_pcr": data.get("total_pcr"),
        "index_pcr": data.get("index_pcr"),
        "trade_date": data.get("trade_date"),
        "fetched_at": fetched_at or _now_iso(),
        "frequency": FREQUENCY,
        "stale_after_hours": stale_after_hours,
        "status": "fresh",
    }


def fetch_page(
    session: requests.Session,
    url: str = CBOE_DAILY_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Fetch the CBOE daily market statistics page."""
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def _fetch_with_retry(
    session: requests.Session,
    url: str,
    timeout: int,
    retries: int,
    backoff: float,
) -> str:
    """Fetch the page with retry and exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return fetch_page(session, url=url, timeout=timeout)
        except (requests.RequestException, ValueError) as error:
            last_error = error
            logger.warning(
                "PCR fetch attempt %d/%d failed: %s", attempt + 1, retries, error
            )
            if attempt < retries - 1:
                time.sleep(backoff * (2**attempt))
    raise RuntimeError(f"PCR fetch failed after {retries} attempts: {last_error}")


def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch and return the equity put/call ratio as a structured dict.

    Args:
        config: Optional overrides (url, timeout, retries, backoff, headers).
    """
    config = config or {}
    url = config.get("url", CBOE_DAILY_URL)
    timeout = config.get("timeout", DEFAULT_TIMEOUT)
    retries = config.get("retries", DEFAULT_RETRIES)
    backoff = config.get("backoff", DEFAULT_BACKOFF)
    headers = config.get("headers", DEFAULT_HEADERS)

    with requests.Session() as session:
        session.headers.update(headers)
        html = _fetch_with_retry(session, url, timeout, retries, backoff)

    data = parse_ratios(html)
    return build_result(
        data,
        stale_after_hours=config.get("stale_after_hours", DEFAULT_STALE_AFTER_HOURS),
    )
