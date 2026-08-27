"""NYSE New Highs/New Lows scraper module.

Fetches the Barchart highs/lows summary page and extracts the NYSE 52-week
new highs and new lows counts (strategy F3/#12). The page embeds the data
as a static HTML table (Period, OVERALL, NYSE, NASDAQ, NYSE Arca, ETFs,
OTC-US). Only the desktop table is used — the page contains a second mobile
copy of the table without ``timeFrame`` anchors, which is skipped.

NOTE: Barchart was previously considered not scrapable (WAF 404). With
browser headers (User-Agent + Referer) the page returns 200 and the data
is in the static HTML. Verified 2026-08-19.

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests

from fetch_utils import log_scrape

logger = logging.getLogger(__name__)

BARCHART_URL = "https://www.barchart.com/stocks/highs-lows/summary"

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
    "Referer": "https://www.barchart.com/",
}


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def parse_highs_lows(html: str) -> dict[str, Any]:
    """Extract NYSE 52-week new highs/lows from the Barchart summary page.

    The page contains two copies of the summary table (desktop + mobile);
    only rows from the desktop table (anchors with ``timeFrame``) are used.
    Returns a dict with nyse_highs_52w, nyse_lows_52w and trade_date.

    Raises:
        ValueError: If the 52-Week NYSE values cannot be found or parsed.
    """
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    values: dict[str, int] = {}
    for row in rows:
        if "timeFrame" not in row:
            continue  # skip the mobile duplicate and header rows
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(tds) < 3:
            continue
        period = re.sub(r"<[^>]+>", "", tds[0]).strip()
        # NYSE is the 2nd data column (OVERALL is 1st; Period is the label td).
        m = re.search(r"<a[^>]*>\s*(\d+)\s*</a>", tds[2])
        if not m:
            continue
        values[period] = int(m.group(1))

    nyse_highs = values.get("52-Week Highs")
    nyse_lows = values.get("52-Week Lows")
    if nyse_highs is None or nyse_lows is None:
        raise ValueError("Barchart page does not contain 52-Week NYSE highs/lows")

    trade_date: str | None = None
    m_date = re.search(
        r"Last Updated:\s*(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}\s*ET", html
    )
    if m_date:
        trade_date = datetime.strptime(m_date.group(1), "%m/%d/%Y").date().isoformat()

    return {
        "nyse_highs_52w": nyse_highs,
        "nyse_lows_52w": nyse_lows,
        "trade_date": trade_date,
    }


def build_result(
    data: dict[str, Any],
    fetched_at: str | None = None,
    stale_after_hours: int = DEFAULT_STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Build the output dict in the file.json format."""
    return {
        "nyse_highs_52w": data.get("nyse_highs_52w"),
        "nyse_lows_52w": data.get("nyse_lows_52w"),
        "trade_date": data.get("trade_date"),
        "fetched_at": fetched_at or _now_iso(),
        "frequency": FREQUENCY,
        "stale_after_hours": stale_after_hours,
        "status": "fresh",
    }


def fetch_page(
    session: requests.Session,
    url: str = BARCHART_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Fetch the Barchart highs/lows summary page."""
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
                "NH-NL fetch attempt %d/%d failed: %s", attempt + 1, retries, error
            )
            if attempt < retries - 1:
                time.sleep(backoff * (2**attempt))
    raise RuntimeError(f"NH-NL fetch failed after {retries} attempts: {last_error}")


@log_scrape("NYSE New Highs/Lows (Barchart)")
def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch and return the NYSE 52-week new highs/lows as a structured dict.

    Args:
        config: Optional overrides (url, timeout, retries, backoff, headers).
    """
    config = config or {}
    url = config.get("url", BARCHART_URL)
    logger.info("  url: %s", url)
    timeout = config.get("timeout", DEFAULT_TIMEOUT)
    retries = config.get("retries", DEFAULT_RETRIES)
    backoff = config.get("backoff", DEFAULT_BACKOFF)
    headers = config.get("headers", DEFAULT_HEADERS)

    with requests.Session() as session:
        session.headers.update(headers)
        html = _fetch_with_retry(session, url, timeout, retries, backoff)

    data = parse_highs_lows(html)
    return build_result(
        data,
        stale_after_hours=config.get("stale_after_hours", DEFAULT_STALE_AFTER_HOURS),
    )
