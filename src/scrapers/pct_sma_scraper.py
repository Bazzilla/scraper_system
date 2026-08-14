"""Percentage above SMA scraper module (sector breadth).

Reads the OHLCV cache written by ``ohlcv_fetcher`` and computes the share of
tickers whose last close is above SMA50 and SMA200, per category and total.
This is the sector breadth used by the buy-the-dip strategy as a macro
confirmation (indicators #13-14): % above SMA50 < 20% = oversold market,
% above SMA200 < 30% = deteriorated market.

NOTE: the original source (IndexIndicators.com) exposes the chart as a PNG
image only — not scrapable. We compute the breadth locally from our own OHLCV
data (sector breadth, more aligned with the strategy's universe).

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ta.trend import SMAIndicator

from scrapers.indicators import records_to_frame

logger = logging.getLogger(__name__)

DEFAULT_SMA_FAST = 50
DEFAULT_SMA_SLOW = 200
DEFAULT_STALE_AFTER_HOURS = 24
FREQUENCY = "daily"


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def load_cache(cache_path: str) -> dict[str, Any]:
    """Load the OHLCV cache JSON from disk.

    Raises:
        FileNotFoundError: If the cache file does not exist.
    """
    path = Path(cache_path)
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def ticker_above_sma(
    records: list[dict[str, Any]],
    sma_fast: int = DEFAULT_SMA_FAST,
    sma_slow: int = DEFAULT_SMA_SLOW,
) -> tuple[bool | None, bool | None]:
    """Return (above_sma50, above_sma200) for a ticker's OHLCV records.

    Each SMA is evaluated independently: a SMA returns None when there is not
    enough data for its window or the last value is missing. A ticker with only
    60 records still gets a valid SMA50 result (None only for SMA200).
    """
    if not records:
        return None, None
    try:
        frame = records_to_frame(records)
    except Exception as error:  # noqa: BLE001 - per-ticker isolation
        logger.warning("pct_sma: frame conversion failed: %s", error)
        return None, None
    close = frame["Close"]
    last_raw = close.iloc[-1]
    if _is_nan(last_raw):
        return None, None
    last_close = float(last_raw)

    def _above(window: int) -> bool | None:
        if len(close) < window:
            return None
        series = SMAIndicator(close=close, window=window).sma_indicator()
        last_sma = series.iloc[-1]
        if last_sma is None or _is_nan(last_sma):
            return None
        return last_close >= float(last_sma)

    return _above(sma_fast), _above(sma_slow)


def _is_nan(value: Any) -> bool:
    """NaN check without importing pandas at call sites."""
    try:
        import math
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return True


def aggregate(
    tickers: dict[str, Any],
    cache: dict[str, Any],
    sma_fast: int = DEFAULT_SMA_FAST,
    sma_slow: int = DEFAULT_SMA_SLOW,
) -> dict[str, dict[str, Any]]:
    """Compute above-SMA counts per category and total.

    Tickers without enough data are excluded from the denominator. Returns
    dict with per-category entries plus a "total" key.
    """
    categories: dict[str, dict[str, Any]] = {}

    def _init() -> dict[str, Any]:
        return {
            "above_sma50": 0,
            "total": 0,
            "pct_sma50": 0.0,
            "above_sma200": 0,
            "pct_sma200": 0.0,
        }

    total_stats = _init()

    for category, entries in tickers.items():
        stats = _init()
        for entry in entries:
            symbol = entry["symbol"]
            records = cache.get(category, {}).get(symbol, [])
            above_fast, above_slow = ticker_above_sma(records, sma_fast, sma_slow)
            if above_fast is None and above_slow is None:
                continue  # dati insufficienti → escluso
            stats["total"] += 1
            total_stats["total"] += 1
            if above_fast is True:
                stats["above_sma50"] += 1
                total_stats["above_sma50"] += 1
            if above_slow is True:
                stats["above_sma200"] += 1
                total_stats["above_sma200"] += 1
        if stats["total"] > 0:
            stats["pct_sma50"] = round(stats["above_sma50"] / stats["total"] * 100, 1)
            stats["pct_sma200"] = round(stats["above_sma200"] / stats["total"] * 100, 1)
        categories[category] = stats

    if total_stats["total"] > 0:
        total_stats["pct_sma50"] = round(total_stats["above_sma50"] / total_stats["total"] * 100, 1)
        total_stats["pct_sma200"] = round(total_stats["above_sma200"] / total_stats["total"] * 100, 1)
    categories["total"] = total_stats
    return categories


def build_result(
    aggregated: dict[str, dict[str, Any]],
    fetched_at: str | None = None,
    stale_after_hours: int = DEFAULT_STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Build the output dict in the file.json format.

    Status is 'fresh' only when at least one ticker was included in the
    breadth; with zero usable data the module reports 'stale' so the
    consolidator does not show a misleading macro signal.
    """
    result: dict[str, Any] = {key: dict(value) for key, value in aggregated.items()}
    result["fetched_at"] = fetched_at or _now_iso()
    result["frequency"] = FREQUENCY
    result["stale_after_hours"] = stale_after_hours
    total_count = aggregated.get("total", {}).get("total", 0)
    result["status"] = "fresh" if total_count > 0 else "stale"
    return result


def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute the sector breadth from the OHLCV cache.

    Args:
        config: Overrides + injected ``tickers`` and ``cache_path``.
    """
    config = config or {}
    tickers = config.get("tickers", {})
    cache_path = config.get("cache_path")
    if not cache_path:
        raise ValueError("pct_sma requires 'cache_path' in config")

    cache = load_cache(cache_path)
    sma_fast = config.get("sma_fast", DEFAULT_SMA_FAST)
    sma_slow = config.get("sma_slow", DEFAULT_SMA_SLOW)
    aggregated = aggregate(tickers, cache, sma_fast=sma_fast, sma_slow=sma_slow)
    return build_result(
        aggregated,
        stale_after_hours=config.get("stale_after_hours", DEFAULT_STALE_AFTER_HOURS),
    )
