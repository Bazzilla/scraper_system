"""Fair-value / valuation scraper module.

Per-ticker fundamental valuation snapshot from Yahoo Finance (yfinance —
already a project dependency for OHLCV). Extracts the multiples and the
analyst target prices used to estimate a margin-of-safety signal:

- trailing/forward P/E, P/B, EV/EBITDA, PEG
- analyst target mean/median/high/low
- ``upside_pct`` = distance of the current price from the median target

DISPLAY-ONLY artifact (registry: coverage=false, like vix_spot): it never
enters the strategy score automatically. Per-ticker failure isolation and
``request_delay`` rate limiting follow the ohlcv_fetcher pattern.

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import yfinance as yf

from fetch_utils import log_scrape
from valuation_store import append_snapshots, bucket_for, bucket_label

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 2.0
DEFAULT_REQUEST_DELAY = 1.0
DEFAULT_STALE_AFTER_HOURS = 24
FREQUENCY = "daily"

# Campi yfinance.info estratti (multiplice + target analisti)
_INFO_FIELDS = (
    "trailingPE",
    "forwardPE",
    "priceToBook",
    "enterpriseToEbitda",
    "trailingPegRatio",
    "targetMeanPrice",
    "targetMedianPrice",
    "targetHighPrice",
    "targetLowPrice",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_valuation(info: dict[str, Any]) -> dict[str, Any]:
    """Build the valuation dict from a raw yfinance ``info`` mapping.

    ``upside_pct`` is computed against the median analyst target using the
    current price (regularMarketPrice/currentPrice). Missing pieces stay
    None — the caller decides fail-closed semantics.
    """
    out: dict[str, Any] = {k: info.get(k) for k in _INFO_FIELDS}
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    out["current_price"] = price
    target = out.get("targetMedianPrice")
    if price and target:
        out["upside_pct"] = round((target - price) / price * 100, 2)
    else:
        out["upside_pct"] = None
    # Bucket descrittivo automatico (validation-mode, display-only)
    out["bucket"] = bucket_for(out["upside_pct"])
    return out


def fetch_info(symbol: str) -> dict[str, Any]:
    """Fetch the raw yfinance info dict for one symbol."""
    ticker = yf.Ticker(symbol)
    return ticker.info or {}


def _fetch_with_retry(symbol: str, retries: int, backoff: float) -> dict[str, Any]:
    """Fetch info with retry and exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            info = fetch_info(symbol)
            if info:
                return info
            raise ValueError(f"empty info for {symbol}")
        except Exception as error:  # noqa: BLE001 - retry su qualunque errore rete/API
            last_error = error
            logger.warning(
                "Valuation fetch attempt %d/%d failed for %s: %s",
                attempt + 1, retries, symbol, error,
            )
            if attempt < retries - 1:
                time.sleep(backoff * (2**attempt))
    raise RuntimeError(f"valuation fetch failed for {symbol}: {last_error}")


def _fetch_all(tickers: dict[str, Any], config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Fetch valuation for all tickers, grouped by category. Per-ticker isolation."""
    retries = config.get("retries", DEFAULT_RETRIES)
    backoff = config.get("backoff", DEFAULT_BACKOFF)
    request_delay = config.get("request_delay", DEFAULT_REQUEST_DELAY)

    fetched: dict[str, dict[str, Any]] = {}
    for category, entries in tickers.items():
        fetched[category] = {}
        for entry in entries:
            symbol = entry.get("symbol", "?")
            try:
                info = _fetch_with_retry(symbol, retries, backoff)
                fetched[category][symbol] = extract_valuation(info)
            except Exception as error:  # noqa: BLE001 - per-ticker isolation
                logger.error("Valuation fetch failed for %s: %s", symbol, error)
            if request_delay > 0:
                time.sleep(request_delay)
    return fetched


def build_result(
    tickers: dict[str, Any],
    fetched: dict[str, dict[str, Any]],
    fetched_at: str | None = None,
    stale_after_hours: int = DEFAULT_STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Build the output dict: {category: {symbol: {...}}}, fail-closed status."""
    fetched_at = fetched_at or _now_iso()
    result: dict[str, Any] = {}
    total = 0
    ok = 0

    for category, entries in tickers.items():
        result[category] = {}
        for entry in entries:
            symbol = entry["symbol"]
            data = fetched.get(category, {}).get(symbol)
            total += 1
            if not data:
                continue
            ok += 1
            payload = {
                "symbol": symbol,
                "name": entry["name"],
                "fetched_at": fetched_at,
                "frequency": FREQUENCY,
                "stale_after_hours": stale_after_hours,
                "status": "fresh",
            }
            payload.update(data)
            result[category][symbol] = payload

    result["status"] = "fresh" if total > 0 and ok == total else "stale"
    return result


@log_scrape("Valuation (fair value)")
def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch valuation snapshots for all configured tickers.

    Validation-mode: quando è presente ``history_path`` (risolto
    dall'orchestrator), ogni run APPEND uno snapshot giornaliero per ticker
    su SQLite (dedup per giorno) — solo raccolta, mai segnale.

    Args:
        config: Overrides + injected ``tickers`` and ``history_path``.
    """
    config = config or {}
    tickers = config.get("tickers", {})
    total = sum(len(v) for v in tickers.values()) if isinstance(tickers, dict) else 0
    logger.info("  tickers: %d (yfinance info)", total)

    fetched = _fetch_all(tickers, config)

    result = build_result(
        tickers,
        fetched,
        stale_after_hours=config.get("stale_after_hours", DEFAULT_STALE_AFTER_HOURS),
    )

    history_path = config.get("history_path")
    if history_path:
        try:
            written = append_snapshots(str(history_path), result)
            logger.info("Valuation history: %d snapshot scritti su %s",
                        written, history_path)
        except Exception as error:  # noqa: BLE001 - la storia non blocca il run
            logger.error("Valuation history write failed: %s", error)

    return result
