"""OHLCV fetcher scraper module.

Fetches daily OHLCV data from Yahoo Finance (via yfinance) for every ticker in
the config ``tickers`` section, serializes it to a JSON cache on disk, and
returns a compact per-ticker summary in the file.json output format.

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from fetch_utils import log_scrape

logger = logging.getLogger(__name__)

DEFAULT_PERIOD = "1y"
DEFAULT_INTERVAL = "1d"
DEFAULT_TIMEOUT = 10
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 2.0
DEFAULT_REQUEST_DELAY = 1.0
DEFAULT_STALE_AFTER_HOURS = 24
FREQUENCY = "daily"


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def fetch_ohlcv(
    symbol: str,
    period: str = DEFAULT_PERIOD,
    interval: str = DEFAULT_INTERVAL,
    timeout: int = DEFAULT_TIMEOUT,
) -> pd.DataFrame:
    """Download OHLCV data for a single symbol via yfinance."""
    df = yf.download(
        symbol,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=True,
        multi_level_index=False,
        timeout=timeout,
    )
    if df is None or df.empty:
        raise ValueError(f"No OHLCV data returned for {symbol}")
    return df


def frame_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a yfinance DataFrame to a list of plain dict records.

    Each record: {date, open, high, low, close, volume}. Dates are ISO strings.
    Rows with missing OHLCV values are dropped.
    """
    clean = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    records: list[dict[str, Any]] = []
    for date, row in clean.iterrows():
        records.append(
            {
                "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            }
        )
    return records


def serialize_cache(cache: dict[str, dict[str, list[dict[str, Any]]]]) -> str:
    """Serialize the OHLCV cache to a JSON string."""
    return json.dumps(cache, indent=2)


def _fetch_ticker_with_retry(
    symbol: str,
    period: str,
    interval: str,
    timeout: int,
    retries: int,
    backoff: float,
) -> pd.DataFrame:
    """Fetch one ticker's OHLCV with retry and exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return fetch_ohlcv(symbol, period=period, interval=interval, timeout=timeout)
        except Exception as error:  # noqa: BLE001 - yfinance raises mixed types
            last_error = error
            logger.warning(
                "OHLCV fetch %s attempt %d/%d failed: %s",
                symbol, attempt + 1, retries, error,
            )
            if attempt < retries - 1:
                time.sleep(backoff * (2**attempt))
    raise RuntimeError(f"OHLCV fetch failed after {retries} attempts: {last_error}")


def _fetch_all(tickers: dict[str, Any], config: dict[str, Any]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Fetch OHLCV for all tickers, grouped by category. Failures per-ticker.

    A configurable ``request_delay`` (seconds) is applied between ticker
    fetches to avoid triggering rate limits at the data source.
    """
    period = config.get("period", DEFAULT_PERIOD)
    interval = config.get("interval", DEFAULT_INTERVAL)
    timeout = config.get("timeout", DEFAULT_TIMEOUT)
    retries = config.get("retries", DEFAULT_RETRIES)
    backoff = config.get("backoff", DEFAULT_BACKOFF)
    request_delay = config.get("request_delay", DEFAULT_REQUEST_DELAY)

    cache: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for category, entries in tickers.items():
        cache[category] = {}
        for entry in entries:
            symbol = entry.get("symbol", "?")
            try:
                df = _fetch_ticker_with_retry(symbol, period, interval, timeout, retries, backoff)
                cache[category][symbol] = frame_to_records(df)
            except Exception as error:  # noqa: BLE001 - per-ticker isolation
                logger.error("OHLCV fetch failed for %s: %s", symbol, error)
            if request_delay > 0:
                time.sleep(request_delay)
    return cache


def build_result(
    tickers: dict[str, Any],
    cache: dict[str, dict[str, list[dict[str, Any]]]],
    fetched_at: str | None = None,
    stale_after_hours: int = DEFAULT_STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Build the output dict in the file.json format.

    One entry per ticker with OHLCV data; tickers without data are omitted.
    The module-level ``status`` is 'fresh' iff every configured ticker has data.
    """
    fetched_at = fetched_at or _now_iso()
    result: dict[str, Any] = {}
    total = 0
    ok = 0

    for category, entries in tickers.items():
        result[category] = {}
        for entry in entries:
            symbol = entry["symbol"]
            records = cache.get(category, {}).get(symbol, [])
            total += 1
            if not records:
                continue
            ok += 1
            result[category][symbol] = {
                "symbol": symbol,
                "name": entry["name"],
                "last_close": records[-1]["close"],
                "last_date": records[-1]["date"],
                "fetched_at": fetched_at,
                "frequency": FREQUENCY,
                "stale_after_hours": stale_after_hours,
                "status": "fresh",
            }

    result["status"] = "fresh" if total > 0 and ok == total else "stale"
    return result


def _save_cache(cache_path: str, cache: dict[str, dict[str, list[dict[str, Any]]]]) -> None:
    """Write the OHLCV cache to disk (creates parent dirs)."""
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_cache(cache), encoding="utf-8")


@log_scrape("OHLCV (Yahoo Finance)")
def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch OHLCV for all configured tickers and save to cache.

    Args:
        config: Overrides + injected ``tickers`` and ``cache_path``.
    """
    config = config or {}
    tickers = config.get("tickers", {})
    total = sum(len(v) for v in tickers.values()) if isinstance(tickers, dict) else 0
    logger.info("  tickers: %d", total)
    cache_path = config.get("cache_path")

    cache = _fetch_all(tickers, config)
    if cache_path:
        _save_cache(cache_path, cache)

    return build_result(
        tickers,
        cache,
        stale_after_hours=config.get("stale_after_hours", DEFAULT_STALE_AFTER_HOURS),
    )
