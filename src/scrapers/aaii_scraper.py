"""AAII Investor Sentiment Survey scraper module.

Fetches the weekly bullish/bearish/neutral percentages from the AAII
sentiment survey page (server-rendered static HTML). The page embeds the
current-week values in the HTML bars; the older ``dataChart5`` JSON block has
been removed by AAII (verified 2026-08-14), so ``html_bars`` is the primary
parse strategy and ``data_chart`` is kept as a legacy fallback in case AAII
restores it. The strategy that succeeded is recorded in the result as
``source`` (``html_bars`` or ``data_chart``).

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from fetch_utils import try_parsers

logger = logging.getLogger(__name__)

AAII_URL = "https://www.aaii.com/sentimentsurvey"

DEFAULT_TIMEOUT = 20
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 2.0
DEFAULT_STALE_AFTER_HOURS = 168  # 7 days (weekly)
FREQUENCY = "weekly"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Regex for the embedded JSON array holding ~52 weeks of history.
_DATA_CHART_RE = re.compile(r"var dataChart5\s*=\s*(\[.*?\]);", re.DOTALL)


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _next_thursday(from_date: datetime) -> str:
    """Return the ISO date of the next Thursday on/after ``from_date``."""
    days_ahead = (3 - from_date.weekday()) % 7  # Thursday == weekday 3
    if days_ahead == 0:
        days_ahead = 7
    return (from_date + timedelta(days=days_ahead)).date().isoformat()


def parse_data_chart(html: str) -> dict[str, Any]:
    """Extract current-week sentiment from the embedded ``dataChart5`` JSON.

    Raises:
        ValueError: If the JSON array is missing or empty.
    """
    match = _DATA_CHART_RE.search(html)
    if match is None:
        raise ValueError("AAII dataChart5 JSON not found in HTML")
    rows = json.loads(match.group(1))
    if not rows:
        raise ValueError("AAII dataChart5 JSON is empty")
    current = rows[0]
    return {
        "bullish": float(current["bullish"]),
        "bearish": float(current["bearish"]),
        "neutral": float(current["neutral"]),
    }


def parse_html_bars(html: str) -> dict[str, Any]:
    """Fallback: parse the current-week percentages from the HTML bars."""
    soup = BeautifulSoup(html, "html.parser")
    block = soup.select_one("div.weekending div.datebars")
    if block is None:
        raise ValueError("AAII weekending bars not found in HTML")

    def _bar_value(cls: str) -> float:
        node = block.select_one(f"div.bar.{cls}")
        if node is None:
            raise ValueError(f"AAII bar {cls!r} not found")
        return float(node.get_text(strip=True).rstrip("%"))

    return {
        "bullish": _bar_value("bullish"),
        "neutral": _bar_value("neutral"),
        "bearish": _bar_value("bearish"),
    }


def build_result(
    bullish: float,
    bearish: float,
    neutral: float,
    fetched_at: str,
) -> dict[str, Any]:
    """Build the output dict in the file.json format."""
    return {
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
        "fetched_at": fetched_at,
        "frequency": FREQUENCY,
        "stale_after_hours": DEFAULT_STALE_AFTER_HOURS,
        "status": "fresh",
        "next_expected": _next_thursday(datetime.now(timezone.utc)),
    }


def fetch_html(
    session: requests.Session,
    url: str = AAII_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Fetch the AAII sentiment page HTML."""
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
    """Fetch HTML with retry and exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return fetch_html(session, url=url, timeout=timeout)
        except (requests.RequestException, ValueError) as error:
            last_error = error
            logger.warning(
                "AAII fetch attempt %d/%d failed: %s", attempt + 1, retries, error
            )
            if attempt < retries - 1:
                time.sleep(backoff * (2**attempt))
    raise RuntimeError(f"AAII fetch failed after {retries} attempts: {last_error}")


def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch and return the AAII sentiment result as a structured dict.

    Args:
        config: Optional overrides (url, timeout, retries, backoff, headers).
    """
    config = config or {}
    url = config.get("url", AAII_URL)
    timeout = config.get("timeout", DEFAULT_TIMEOUT)
    retries = config.get("retries", DEFAULT_RETRIES)
    backoff = config.get("backoff", DEFAULT_BACKOFF)
    headers = config.get("headers", DEFAULT_HEADERS)

    with requests.Session() as session:
        session.headers.update(headers)
        html = _fetch_with_retry(session, url, timeout, retries, backoff)

    data, parser_name = try_parsers(
        html,
        [("html_bars", parse_html_bars), ("data_chart", parse_data_chart)],
    )
    logger.info("AAII source: %s", parser_name)
    result = build_result(
        data["bullish"], data["bearish"], data["neutral"], _now_iso()
    )
    result["source"] = parser_name
    return result