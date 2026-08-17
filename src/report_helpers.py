"""Shared helper functions and constants for the HTML report generator.

This module is a leaf module (no dependencies on other report_* modules). It
holds the pure formatting/classification helpers used by the report cards,
tables and legend modules.
"""

from __future__ import annotations

import html as html_mod
from datetime import datetime
from typing import Any

_FGI_ZONES = [
    (25, "extreme_fear"),
    (45, "fear"),
    (56, "neutral"),
    (75, "greed"),
    (101, "extreme_greed"),
]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def semaphore_class(value: float | None, metric: str) -> str:
    """Return the CSS class for a metric's semaphore."""
    if value is None:
        return "neutral"
    if metric == "rsi":
        if value > 70:
            return "overbought"
        if value < 30:
            return "oversold"
        return "neutral"
    if metric == "mfi":
        if value > 80:
            return "overbought"
        if value < 20:
            return "oversold"
        return "neutral"
    if metric == "drawdown":
        if value >= -5:
            return "ok"
        if value >= -15:
            return "warning"
        return "critical"
    return "neutral"


def market_regime(fgi_score: float | None) -> str:
    """Classify the market regime from the Fear & Greed score.

    Returns 'greed', 'fear' or 'neutral'. Missing score → 'neutral' (no gate).
    Boundaries follow the strategy (F1): Greed starts at 56, Fear up to 45.
    """
    if fgi_score is None:
        return "neutral"
    if fgi_score >= 56:
        return "greed"
    if fgi_score <= 45:
        return "fear"
    return "neutral"


def compute_signal(
    entry: dict[str, Any],
    regime: str = "neutral",
    proxy_accepted: set[str] | frozenset[str] | None = None,
) -> str:
    """Compute a trading signal from a ticker's indicators and market regime.

    Follows the project's trading strategy (buy-the-dip): technical weakness
    (price below SMAs, deep drawdown) is the SCREENING INPUT for a potential
    entry, not a sell reason. A sell is only justified by an explicit exit
    trigger (take-profit, fundamental deterioration, time-stop — Regola 4),
    which the dashboard cannot compute from price data alone.

    Scoring (per indicator, +1 bullish / -1 bearish):
    - RSI < 30 (oversold) → +1 ; RSI > 70 (overbought) → -1
    - MFI < 20 (oversold) → +1 ; MFI > 80 (overbought) → -1
    - price above SMA50 → +1 ; below → -1
    - price above SMA200 → +1 ; below → -1
    - drawdown >= -5 (near high) → +1 ; < -15 (critical) → -1

    Classes:
    - 'buy'       (score >= +2): convergence of oversold + strength
    - 'watchlist' (score <= -2): deep weakness — the buy-the-dip profile, but
                   NOT a sell reason. Watch, do not enter without confirmations.
    - 'hold'      otherwise: mixed signals / no opportunity.

    Market gate (Regola 0): in GREED no 'buy' (do not chase a hot market); in
    FEAR deep weakness stays 'watchlist' (discounts are more real). The gate
    never produces a sell.

    Proxy guard (audit 2026-08-14): this scorer consumes only IMPLEMENTED
    per-ticker indicators (rsi_14, mfi_14, sma_50, sma_200, drawdown_52w from
    the OHLCV cache). Proxy indicators (VIX spot, sector breadth) are NOT
    passed here and must never be treated as the original strategy indicator.
    If a caller wants a proxy to influence scoring, it must do so explicitly
    via ``proxy_accepted`` and the strategy indicator registry; the market
    regime gate uses the FGI (implemented), never a proxy FGI variant.
    """
    accepted = set(proxy_accepted or ())
    score = 0

    rsi = entry.get("rsi_14")
    if rsi is not None:
        if rsi < 30:
            score += 1
        elif rsi > 70:
            score -= 1

    mfi = entry.get("mfi_14")
    if mfi is not None:
        if mfi < 20:
            score += 1
        elif mfi > 80:
            score -= 1

    price = entry.get("last_close")
    sma50 = entry.get("sma_50")
    if price is not None and sma50 is not None:
        score += 1 if price >= sma50 else -1

    sma200 = entry.get("sma_200")
    if price is not None and sma200 is not None:
        score += 1 if price >= sma200 else -1

    drawdown = entry.get("drawdown_52w")
    if drawdown is not None:
        if drawdown >= -5:
            score += 1
        elif drawdown < -15:
            score -= 1

    if score >= 2:
        signal = "buy"
    elif score <= -2:
        signal = "watchlist"
    else:
        signal = "hold"

    # Market gate (Regola 0): climate must point in the same direction.
    if regime == "greed" and signal == "buy":
        return "hold"
    return signal


def _signal_badge(signal: str) -> str:
    """Render the signal badge for a ticker."""
    cls = {"buy": "buy", "watchlist": "watchlist", "hold": "hold"}[signal]
    label = {"buy": "COMPRA", "watchlist": "WATCHLIST", "hold": "ATTENDI"}[signal]
    icon = {"buy": "🟢", "watchlist": "🟠", "hold": "⚪"}[signal]
    return f'<span class="signal {cls}">{icon} {label}</span>'


_ITALIAN_MONTHS = [
    "gen", "feb", "mar", "apr", "mag", "giu",
    "lug", "ago", "set", "ott", "nov", "dic",
]


def format_iso_dt(iso: str | None) -> str:
    """Format an ISO timestamp into a readable Italian datetime string."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        month = _ITALIAN_MONTHS[dt.month - 1]
        return f"{dt.day:02d} {month} {dt.year}, {dt.hour:02d}:{dt.minute:02d}"
    except ValueError:
        return iso


def fmt(value: float | None) -> str:
    """Format a number, or return an em-dash for None."""
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def _badge(status: str) -> str:
    cls = "fresh" if status == "fresh" else "stale"
    return f'<span class="badge {cls}">{html_mod.escape(status)}</span>'


def _fgi_rating_badge(rating: str) -> str:
    """Render a FGI component rating badge (fear/greed/neutral...)."""
    cls = html_mod.escape(rating.strip().lower().replace(" ", "_"))
    return f'<span class="sema {cls}">{html_mod.escape(rating)}</span>'


def _age_attrs(fetched_at: str | None, stale_after_hours: float | None) -> str:
    """Return HTML data-* attributes for client-side age computation.

    Returns a string like `` data-fetched-at="..." data-stale-hours="..."``
    (leading space included) or an empty string when the timestamp or the
    validity window is missing.
    """
    if not fetched_at or stale_after_hours is None:
        return ""
    iso = html_mod.escape(fetched_at)
    return f' data-fetched-at="{iso}" data-stale-hours="{stale_after_hours}"'


def _sema(value: float | None, metric: str) -> str:
    cls = semaphore_class(value, metric)
    badge = "" if cls in ("", "neutral") else f'<span class="sema {cls}">{cls}</span>'
    if badge:
        # Layout flessibile: valore a sinistra, badge a destra (ben separati).
        return (
            f'<span class="sema-cell">'
            f'<span class="sema-val">{fmt(value)}</span>{badge}'
            f"</span>"
        )
    return f'<span class="sema-val">{fmt(value)}</span>'


def _status_badge(status: str) -> str:
    """Render a strategy-coverage status badge.

    Handles implementation_status values (implemented/proxy/missing/
    manual_supported) and runtime source values (scraped/manual/missing).
    """
    if status in ("implemented", "scraped"):
        cls, label = "sema ok", status
    elif status in ("proxy", "manual", "manual_supported"):
        cls, label = "sema warning", status
    else:
        cls, label = "sema critical", status
    return f'<span class="sema {cls}">{html_mod.escape(label)}</span>'
