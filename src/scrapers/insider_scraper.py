"""Insider transactions scraper module.

Reads the OpenInsider "Latest Officer Purchases $25k+" page and computes the
insider-buying bonus of the buy-the-dip strategy (specifiche_strategia.md H5):
- +0.5 if >= 2 officer open-market purchases in the last 30 days, value > $100K
- +1.0 if a CEO/CFO purchased on the open market
- cumulative, capped at +1.5

NOTE: OpenInsider only answers over HTTP (HTTPS connection is refused by the
server). The officer page already includes CEO/CFO transactions, identified by
the Title column, so a single page is scanned.

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

OPENINSIDER_OFFICER_URL = "http://openinsider.com/latest-officer-purchases-25k"

DEFAULT_TIMEOUT = 20
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 2.0
DEFAULT_DAYS_BACK = 30
DEFAULT_MIN_VALUE = 100000
DEFAULT_STALE_AFTER_HOURS = 24
FREQUENCY = "daily"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_CEO_CFO_ROLES = re.compile(
    r"\b(CEO|CFO|Chief Executive Officer|Chief Financial Officer)\b", re.IGNORECASE
)


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _num(value: str) -> float:
    """Parse a formatted number like '+80,000' or '+$401,851' to float."""
    cleaned = value.replace("$", "").replace(",", "").replace("+", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_rows(html: str) -> list[dict[str, Any]]:
    """Extract transaction rows from the OpenInsider results table.

    Parsing is done with BeautifulSoup because the real rows contain ``>``
    inside an ``onmouseover`` attribute (ToolTip), which breaks regex-based
    cell splitting. The table has 17 cells per row in this column order:
    X, Filing Date, Trade Date, Ticker, Company Name, Insider Name, Title,
    Trade Type, Price, Qty, Owned, DeltaOwn, Value, 1d, 1w, 1m, 6m.

    Returns a list of dicts with ticker, insider, role, trade_type, price,
    qty, value and trade_date.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    # Scoping alla tabella dei risultati (classe nota) per evitare righe
    # spurie da altre tabelle della pagina.
    for tr in soup.select("table.tinytable tr"):
        cells = tr.find_all("td")
        if len(cells) < 13:
            continue
        ticker_a = cells[3].find("a", href=True)
        if not ticker_a:
            continue
        ticker = ticker_a.get_text(strip=True)
        if not ticker:
            continue
        trade_date = cells[2].get_text(strip=True)
        rows.append(
            {
                "ticker": ticker,
                "insider": cells[5].get_text(strip=True),
                "role": cells[6].get_text(strip=True),
                "trade_type": cells[7].get_text(strip=True),
                "price": _num(cells[8].get_text(strip=True)),
                "qty": _num(cells[9].get_text(strip=True)),
                "value": _num(cells[12].get_text(strip=True)),
                "trade_date": trade_date,
            }
        )
    return rows


def filter_recent(rows: list[dict[str, Any]], days_back: int = DEFAULT_DAYS_BACK) -> list[dict[str, Any]]:
    """Keep only open-market purchases within the last days_back days."""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days_back)
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if row["trade_type"] != "P - Purchase":
            continue
        try:
            trade_date = datetime.strptime(row["trade_date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if trade_date >= cutoff:
            filtered.append(row)
    return filtered


def compute_bonuses(
    rows: list[dict[str, Any]],
    tickers: dict[str, Any],
    min_value: int = DEFAULT_MIN_VALUE,
) -> dict[str, dict[str, Any]]:
    """Compute insider bonuses per configured ticker.

    Returns dict keyed by category with per-ticker stats, plus a "total" key.
    """
    result: dict[str, dict[str, Any]] = {}
    all_tickers_with_bonus: list[tuple[str, float]] = []

    for category, entries in tickers.items():
        result[category] = {}
        for entry in entries:
            symbol = entry["symbol"]
            # The bonus is defined over open-market purchases only: filter out
            # sales (S - ...) so the pure function stays correct even when it
            # receives rows that include sales. Date filtering is the caller's
            # responsibility (see filter_recent).
            purchases = [
                r
                for r in rows
                if r["ticker"] == symbol and r["trade_type"] == "P - Purchase"
            ]
            if not purchases:
                continue
            total_value = sum(r["value"] for r in purchases)
            ceo_cfo = any(_CEO_CFO_ROLES.search(r["role"]) for r in purchases)
            officer_bonus = 0.5 if (len(purchases) >= 2 and total_value > min_value) else 0.0
            ceo_cfo_bonus = 1.0 if ceo_cfo else 0.0
            total_bonus = round(min(officer_bonus + ceo_cfo_bonus, 1.5), 1)
            result[category][symbol] = {
                "purchases_30d": len(purchases),
                "total_value_30d": int(total_value),
                "ceo_cfo": ceo_cfo,
                "officer_bonus": officer_bonus,
                "ceo_cfo_bonus": ceo_cfo_bonus,
                "total_bonus": total_bonus,
                "last_trade_date": max(r["trade_date"] for r in purchases),
            }
            if total_bonus > 0:
                all_tickers_with_bonus.append((symbol, total_bonus))

    if all_tickers_with_bonus:
        max_ticker, max_bonus = max(all_tickers_with_bonus, key=lambda x: x[1])
        result["total"] = {
            "tickers_with_bonus": len(all_tickers_with_bonus),
            "max_bonus": max_bonus,
            "max_ticker": max_ticker,
        }
    else:
        result["total"] = {"tickers_with_bonus": 0, "max_bonus": 0.0, "max_ticker": None}
    return result


def build_result(
    per_ticker: dict[str, dict[str, Any]],
    fetched_at: str | None = None,
    stale_after_hours: int = DEFAULT_STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Build the output dict in the file.json format."""
    result: dict[str, Any] = {key: dict(value) for key, value in per_ticker.items()}
    result["fetched_at"] = fetched_at or _now_iso()
    result["frequency"] = FREQUENCY
    result["stale_after_hours"] = stale_after_hours
    result["status"] = "fresh"
    return result


def fetch_page(
    session: requests.Session,
    url: str = OPENINSIDER_OFFICER_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Fetch the OpenInsider officer purchases page (HTTP)."""
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
                "Insider fetch attempt %d/%d failed: %s", attempt + 1, retries, error
            )
            if attempt < retries - 1:
                time.sleep(backoff * (2**attempt))
    raise RuntimeError(f"Insider fetch failed after {retries} attempts: {last_error}")


def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch insider purchases and compute the strategy bonus.

    Args:
        config: Overrides + injected ``tickers``.
    """
    config = config or {}
    tickers = config.get("tickers", {})
    url = config.get("url", OPENINSIDER_OFFICER_URL)
    timeout = config.get("timeout", DEFAULT_TIMEOUT)
    retries = config.get("retries", DEFAULT_RETRIES)
    backoff = config.get("backoff", DEFAULT_BACKOFF)
    headers = config.get("headers", DEFAULT_HEADERS)
    days_back = config.get("days_back", DEFAULT_DAYS_BACK)
    min_value = config.get("min_value", DEFAULT_MIN_VALUE)

    with requests.Session() as session:
        session.headers.update(headers)
        html = _fetch_with_retry(session, url, timeout, retries, backoff)

    rows = parse_rows(html)
    recent = filter_recent(rows, days_back=days_back)
    per_ticker = compute_bonuses(recent, tickers, min_value=min_value)
    return build_result(
        per_ticker,
        stale_after_hours=config.get("stale_after_hours", DEFAULT_STALE_AFTER_HOURS),
    )
