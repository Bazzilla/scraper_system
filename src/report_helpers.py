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
    if metric == "upside":
        # Upside vs target mediano analisti (fair value, display-only):
        # ≥ +20% = sconto interessante (ok), ≤ -10% = titolo caro (critical).
        if value >= 20:
            return "ok"
        if value <= -10:
            return "critical"
        return "neutral"
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


# Buy-the-Dip gate states (audit 2026-08-19). Descriptive market_regime()
# (fear/neutral/greed) is separate from this OPERATIONAL gate: it decides
# whether a technical BUY may stand, degrade to WATCHLIST, or be blocked.
GATE_MISSING_OR_STALE = "missing_or_stale"
GATE_CLOSED = "closed"
GATE_WATCH_ONLY = "watch_only"
GATE_OPEN = "open"
GATE_STRONG_OPEN = "strong_open"


def buy_the_dip_gate(fgi_score: float | str | None, stale: bool = False) -> str:
    """Operational Buy-the-Dip gate from the Fear & Greed score.

    Decides whether a technical BUY is operable. This is the strategy gate
    (separate from the descriptive ``market_regime`` classification):

    - missing/None/non-numeric/stale  → ``missing_or_stale`` (no BUY)
    - fgi_score > 40                  → ``closed`` (no BUY)
    - 25 < fgi_score <= 40            → ``watch_only`` (BUY → WATCHLIST)
    - 20 < fgi_score <= 25            → ``open`` (BUY allowed)
    - fgi_score <= 20                 → ``strong_open`` (BUY allowed, no
      additional operational distinction yet)

    ``stale`` is an explicit freshness flag; when True the gate is
    ``missing_or_stale`` regardless of the score (fail-closed).
    """
    if stale or fgi_score is None or not isinstance(fgi_score, (int, float)):
        return GATE_MISSING_OR_STALE
    if fgi_score > 40:
        return GATE_CLOSED
    if fgi_score > 25:
        return GATE_WATCH_ONLY
    if fgi_score > 20:
        return GATE_OPEN
    return GATE_STRONG_OPEN


def technical_signal(entry: dict[str, Any]) -> str:
    """Technical evaluation of a ticker from its LOCAL indicators only.

    Pure per-ticker scoring (no market gate): RSI, MFI, price vs SMA50,
    price vs SMA200, drawdown 52w. Returns:
    - 'bullish' (score >= +2): convergence of oversold + strength
    - 'weak'    (score <= -2): deep weakness — the buy-the-dip profile, but
                 NOT a sell reason. Watch, do not enter without confirmations.
    - 'neutral' otherwise: mixed signals / no opportunity.

    This is the SCREENING INPUT for a potential entry, not the final action.
    The final decision is made by ``final_action`` after the market gate.
    """
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
        return "bullish"
    if score <= -2:
        return "weak"
    return "neutral"


def final_action(technical: str, gate: str) -> str:
    """Combine a technical setup and the market gate into the final action.

    Mapping (buy-the-dip strategy):
    - technical 'bullish' + gate closed/missing_or_stale → 'hold'
    - technical 'bullish' + gate watch_only              → 'watchlist'
    - technical 'bullish' + gate open/strong_open        → 'buy'
    - technical 'neutral'                                → 'hold'
    - technical 'weak'                                   → 'watchlist'
      (deep weakness is the buy-the-dip profile, never upgraded to 'buy')

    Never produces a sell: a sell requires an explicit exit trigger
    (take-profit, fundamental deterioration, time-stop — Regola 4) that the
    dashboard cannot compute from price data alone.
    """
    if technical == "bullish":
        if gate in (GATE_MISSING_OR_STALE, GATE_CLOSED):
            return "hold"
        if gate == GATE_WATCH_ONLY:
            return "watchlist"
        return "buy"
    if technical == "weak":
        return "watchlist"
    return "hold"


def compute_signal(
    entry: dict[str, Any],
    regime: str = "neutral",
    proxy_accepted: set[str] | frozenset[str] | None = None,
    fgi_score: float | None = None,
) -> str:
    """Compute the final trading signal for a ticker (compatibility wrapper).

    Pipeline: ``technical_signal(entry)`` → market gate
    (``buy_the_dip_gate(fgi_score)``) → ``final_action(technical, gate)``.

    Follows the project's trading strategy (buy-the-dip): technical weakness
    (price below SMAs, deep drawdown) is the SCREENING INPUT for a potential
    entry, not a sell reason. A sell is only justified by an explicit exit
    trigger (take-profit, fundamental deterioration, time-stop — Regola 4),
    which the dashboard cannot compute from price data alone.

    Market gate (Regola 0): in GREED no 'buy' (do not chase a hot market); in
    FEAR deep weakness stays 'watchlist' (discounts are more real). The gate
    never produces a sell.

    Buy-the-Dip FGI gate (audit 2026-08-19): a technical BUY is only operable
    in sufficient fear. The operational gate is delegated to
    ``buy_the_dip_gate(fgi_score)`` (missing/stale → no BUY; > 40 → no BUY;
    25 < FGI <= 40 → WATCHLIST; <= 25 → BUY stays). Non-buy signals are never
    upgraded to 'buy'.

    Proxy guard (audit 2026-08-14): this scorer consumes only IMPLEMENTED
    per-ticker indicators (rsi_14, mfi_14, sma_50, sma_200, drawdown_52w from
    the OHLCV cache). Proxy indicators (VIX spot, sector breadth) are NOT
    passed here and must never be treated as the original strategy indicator.
    If a caller wants a proxy to influence scoring, it must do so explicitly
    via ``proxy_accepted`` and the strategy indicator registry; the market
    regime gate uses the FGI (implemented), never a proxy FGI variant.
    """
    accepted = set(proxy_accepted or ())
    technical = technical_signal(entry)

    # Market gate (Regola 0): climate must point in the same direction.
    if regime == "greed" and technical == "bullish":
        return "hold"

    gate = buy_the_dip_gate(fgi_score)
    return final_action(technical, gate)


def _clamp01(v: float) -> float:
    """Clamp a value to the [0, 1] interval."""
    return max(0.0, min(1.0, v))


def attrattiva_score(
    entry: dict[str, Any],
    fgi_score: float | None = None,
    regime: str = "neutral",
) -> int:
    """Continuous 0-100 buy-the-dip attractiveness score for a ticker.

    Numeric, sortable counterpart of the categorical Segnale, ALIGNED with
    it by construction: the score band comes from the signal itself, so
    ordering a table by this value groups the signal badges in papability
    order (ATTENDI at the bottom, OSSERVA in the middle, VALUTA INGRESSO
    on top). Within the same band, a continuous technical sub-score orders
    tickers sharing the same signal.

    Band (from ``compute_signal`` — same inputs, same pipeline):
    - buy       (VALUTA INGRESSO) → 70-99
    - watchlist (OSSERVA)         → 40-69
    - hold      (ATTENDI)         → 10-39

    Technical sub-score (0-29 within each band): the continuous dip
    component, normalized from 0-60:
    - RSI dip (max 15):  15 * clamp((45 - rsi) / 25, 0, 1)   → rsi ≤ 20 full
    - MFI dip (max 10):  10 * clamp((35 - mfi) / 20, 0, 1)   → mfi ≤ 15 full
    - Drawdown (max 15): 15 * clamp(-drawdown_52w / 30, 0, 1) → dd ≤ -30% full
    - Strength support: price ≥ SMA50 → 10, price ≥ SMA200 → 10

    Fail-closed: missing indicator → 0 points for that component; missing/
    stale FGI → gate blocks the buy band (hold/watchlist only); no data at
    all → 10 (bottom of the ATTENDI band).

    The Segnale column remains the categorical reference; Attrattiva is its
    continuous version, NOT an operational order.
    """
    signal = compute_signal(entry, regime, fgi_score=fgi_score)

    rsi = entry.get("rsi_14")
    mfi = entry.get("mfi_14")
    price = entry.get("last_close")
    sma50 = entry.get("sma_50")
    sma200 = entry.get("sma_200")
    drawdown = entry.get("drawdown_52w")

    tech = 0.0
    if isinstance(rsi, (int, float)):
        tech += 15 * _clamp01((45 - rsi) / 25)
    if isinstance(mfi, (int, float)):
        tech += 10 * _clamp01((35 - mfi) / 20)
    if isinstance(drawdown, (int, float)):
        tech += 15 * _clamp01(-drawdown / 30)
    if isinstance(price, (int, float)) and isinstance(sma50, (int, float)):
        if price >= sma50:
            tech += 10
    if isinstance(price, (int, float)) and isinstance(sma200, (int, float)):
        if price >= sma200:
            tech += 10

    sub = round(tech / 60 * 29)
    base = {"buy": 70, "watchlist": 40, "hold": 10}[signal]
    return base + sub


def _signal_badge(signal: str) -> str:
    """Render the signal badge for a ticker.

    Labels are deliberately non-operational: the report signals setups to
    EVALUATE, it never issues buy orders (buy-the-dip strategy with FGI gate).
    """
    cls = {"buy": "buy", "watchlist": "watchlist", "hold": "hold"}[signal]
    label = {"buy": "VALUTA INGRESSO", "watchlist": "OSSERVA", "hold": "ATTENDI"}[signal]
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


def _collapsible(title: str, content: str) -> str:
    """Wrap a report section in a collapsible <details> (open by default).

    The section title is rendered as an <h2> inside the <summary>, so every
    H2-headed section of the report becomes toggleable. The global
    "Apri tutte/Chiudi tutte" control (see report_html) targets these
    ``details.section`` elements.
    """
    return (
        '<details class="section" open>'
        f"<summary><h2>{title}</h2></summary>"
        f'<div class="section-body">{content}</div>'
        "</details>"
    )


# Pagina → (href, label). Ordine = ordine di visualizzazione nel menù.
_NAV_ITEMS = [
    ("report", "/report.html", "📊 Report"),
    ("overrides", "/overrides.html", "✍️ Immissione manuale"),
    ("tickers", "/tickers.html", "📋 Ticker"),
    ("portfolio", "/portfolio.html", "💼 Portfolio"),
    ("scraper-run", "/scraper-run.html", "🚀 Scraping"),
]

# Favicon condivisa da tutte le pagine: mini grafico a barre con i colori dei
# semafori della dashboard (verde/giallo/rosso su card scura). SVG inline
# data-URI → nessun file binario da servire.
FAVICON_SVG = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "viewBox='0 0 32 32'%3E"
    "%3Crect width='32' height='32' rx='7' fill='%231a212b'/%3E"
    "%3Crect x='6' y='17' width='5' height='9' rx='1' fill='%232ea043'/%3E"
    "%3Crect x='13.5' y='11' width='5' height='15' rx='1' fill='%23d29922'/%3E"
    "%3Crect x='21' y='6' width='5' height='20' rx='1' fill='%23f85149'/%3E"
    "%3C/svg%3E"
)
FAVICON_LINK = f'<link rel="icon" type="image/svg+xml" href="{FAVICON_SVG}">'


def render_nav(active: str) -> str:
    """Render the horizontal page-navigation menu shared by all HTML pages.

    ``active`` is the key of the current page ("report" | "overrides" |
    "tickers"); the matching link gets the ``active`` highlight. Compact
    horizontal button group — no vertical space cost.
    """
    links = "".join(
        f'<a href="{href}" class="{"nav-link active" if key == active else "nav-link"}">'
        f"{label}</a>"
        for key, href, label in _NAV_ITEMS
    )
    return f'<nav class="page-nav">{links}</nav>'
