"""VIX spot (CBOE Volatility Index) scraper module.

Fetches the current VIX index value from CBOE's official daily history CSV.

NOTE: Scope changed from "VIX term structure (M1/M2)" to "VIX spot" because
vixcentral.com is no longer scrapable (Flask session gate not reproducible
with requests). CBOE is the official, free, updated source.

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import csv
import io
import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests

from fetch_utils import log_scrape

logger = logging.getLogger(__name__)

CBOE_VIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"

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
}


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def parse_csv(csv_text: str) -> dict[str, Any]:
    """Extract the latest VIX close from the CBOE CSV.

    The CSV has a header row (DATE,OPEN,HIGH,LOW,CLOSE); the last data row is
    the most recent trading day.

    Raises:
        ValueError: If the CSV is empty or has no data rows.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        raise ValueError("CBOE VIX CSV has no data rows")
    latest = rows[-1]
    return {
        "date": latest["DATE"],
        "vix_close": float(latest["CLOSE"]),
    }


def build_result(vix_close: float, fetched_at: str) -> dict[str, Any]:
    """Build the output dict in the file.json format."""
    return {
        "vix_close": vix_close,
        "fetched_at": fetched_at,
        "frequency": FREQUENCY,
        "stale_after_hours": DEFAULT_STALE_AFTER_HOURS,
        "status": "fresh",
    }


def fetch_csv(
    session: requests.Session,
    url: str = CBOE_VIX_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Fetch the CBOE VIX history CSV."""
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
    """Fetch CSV with retry and exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return fetch_csv(session, url=url, timeout=timeout)
        except (requests.RequestException, ValueError) as error:
            last_error = error
            logger.warning(
                "VIX fetch attempt %d/%d failed: %s", attempt + 1, retries, error
            )
            if attempt < retries - 1:
                time.sleep(backoff * (2**attempt))
    raise RuntimeError(f"VIX fetch failed after {retries} attempts: {last_error}")


@log_scrape("VIX spot (CBOE)")
def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch and return the VIX spot result as a structured dict.

    Args:
        config: Optional overrides (url, timeout, retries, backoff, headers).
    """
    config = config or {}
    url = config.get("url", CBOE_VIX_URL)
    logger.info("  url: %s", url)
    timeout = config.get("timeout", DEFAULT_TIMEOUT)
    retries = config.get("retries", DEFAULT_RETRIES)
    backoff = config.get("backoff", DEFAULT_BACKOFF)
    headers = config.get("headers", DEFAULT_HEADERS)

    with requests.Session() as session:
        session.headers.update(headers)
        csv_text = _fetch_with_retry(session, url, timeout, retries, backoff)

    data = parse_csv(csv_text)
    return build_result(data["vix_close"], _now_iso())