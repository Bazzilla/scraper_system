"""Technical indicators scraper module.

Reads the OHLCV cache written by ``ohlcv_fetcher`` and computes technical
indicators (RSI, OBV, MFI, SMA50, SMA200, drawdown 52w) using the ``ta``
library. Returns a dict in the file.json output format.

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
from ta.volume import (
    OnBalanceVolumeIndicator,
    money_flow_index,
)

logger = logging.getLogger(__name__)

DEFAULT_RSI_WINDOW = 14
DEFAULT_MFI_WINDOW = 14
DEFAULT_SMA_FAST = 50
DEFAULT_SMA_SLOW = 200
DEFAULT_DRAWDOWN_WINDOW = 252
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


def records_to_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert a list of OHLCV record dicts to a pandas DataFrame.

    Column names are normalized to TitleCase (Open, High, Low, Close, Volume)
    to match the conventions used by yfinance and the ``ta`` library.
    """
    frame = pd.DataFrame(records)
    frame = frame.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date").sort_index()
    return frame


def compute_indicators(
    frame: pd.DataFrame,
    rsi_window: int = DEFAULT_RSI_WINDOW,
    mfi_window: int = DEFAULT_MFI_WINDOW,
    sma_fast: int = DEFAULT_SMA_FAST,
    sma_slow: int = DEFAULT_SMA_SLOW,
    drawdown_window: int = DEFAULT_DRAWDOWN_WINDOW,
) -> dict[str, Any]:
    """Compute technical indicators from an OHLCV DataFrame.

    Returns the latest values: rsi_14, obv, mfi_14, sma_50, sma_200,
    drawdown_52w. Missing values (insufficient data) are None.
    """
    close = frame["Close"]
    high = frame["High"]
    low = frame["Low"]
    volume = frame["Volume"]

    rsi_series = RSIIndicator(close=close, window=rsi_window).rsi()
    sma_fast_series = SMAIndicator(close=close, window=sma_fast).sma_indicator()
    sma_slow_series = SMAIndicator(close=close, window=sma_slow).sma_indicator()
    obv_series = OnBalanceVolumeIndicator(close=close, volume=volume).on_balance_volume()
    mfi_series = money_flow_index(high, low, close, volume, window=mfi_window)

    rolling_max = close.rolling(window=drawdown_window, min_periods=1).max()
    drawdown = (close - rolling_max) / rolling_max * 100.0

    def _last(series: pd.Series) -> float | None:
        value = series.iloc[-1]
        if pd.isna(value):
            return None
        return round(float(value), 4)

    return {
        "rsi_14": _last(rsi_series),
        "obv": _last(obv_series),
        "mfi_14": _last(mfi_series),
        "sma_50": _last(sma_fast_series),
        "sma_200": _last(sma_slow_series),
        "drawdown_52w": _last(drawdown),
    }


def build_result(
    tickers: dict[str, Any],
    indicators_by_ticker: dict[str, dict[str, Any]],
    fetched_at: str | None = None,
    stale_after_hours: int = DEFAULT_STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Build the output dict in the file.json format.

    One entry per ticker with indicators; tickers without indicators are
    omitted. The module-level ``status`` is 'fresh' iff every configured
    ticker has indicators.
    """
    fetched_at = fetched_at or _now_iso()
    result: dict[str, Any] = {}
    total = 0
    ok = 0

    for category, entries in tickers.items():
        result[category] = {}
        for entry in entries:
            symbol = entry["symbol"]
            total += 1
            ind = indicators_by_ticker.get(symbol)
            if not ind:
                continue
            ok += 1
            entry_result = dict(ind)
            entry_result.update(
                {
                    "symbol": symbol,
                    "name": entry["name"],
                    "fetched_at": fetched_at,
                    "frequency": FREQUENCY,
                    "stale_after_hours": stale_after_hours,
                    "status": "fresh",
                }
            )
            result[category][symbol] = entry_result

    result["status"] = "fresh" if total > 0 and ok == total else "stale"
    return result


def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute indicators from the OHLCV cache.

    Args:
        config: Overrides + injected ``tickers`` and ``cache_path``.
    """
    config = config or {}
    tickers = config.get("tickers", {})
    cache_path = config.get("cache_path")
    if not cache_path:
        raise ValueError("indicators requires 'cache_path' in config")

    cache = load_cache(cache_path)
    rsi_window = config.get("rsi_window", DEFAULT_RSI_WINDOW)
    mfi_window = config.get("mfi_window", DEFAULT_MFI_WINDOW)
    sma_fast = config.get("sma_fast", DEFAULT_SMA_FAST)
    sma_slow = config.get("sma_slow", DEFAULT_SMA_SLOW)
    drawdown_window = config.get("drawdown_window", DEFAULT_DRAWDOWN_WINDOW)

    indicators_by_ticker: dict[str, dict[str, Any]] = {}
    for category, entries in tickers.items():
        for entry in entries:
            symbol = entry["symbol"]
            records = cache.get(category, {}).get(symbol, [])
            if not records:
                continue
            try:
                frame = records_to_frame(records)
                indicators_by_ticker[symbol] = compute_indicators(
                    frame,
                    rsi_window=rsi_window,
                    mfi_window=mfi_window,
                    sma_fast=sma_fast,
                    sma_slow=sma_slow,
                    drawdown_window=drawdown_window,
                )
            except Exception as error:  # noqa: BLE001 - per-ticker isolation
                logger.error("Indicator computation failed for %s: %s", symbol, error)

    return build_result(
        tickers,
        indicators_by_ticker,
        stale_after_hours=config.get("stale_after_hours", DEFAULT_STALE_AFTER_HOURS),
    )
