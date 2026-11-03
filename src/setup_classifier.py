"""Setup-type classification and buy-candidate flag (orthogonal to the signal).

Pure functions: classify each ticker's technical SETUP
(``PULLBACK_IN_TREND`` / ``TREND_CONTINUATION`` / ``INCOME_DEFENSIVE`` /
``UNKNOWN``), derive the informational ``value_flag`` from valuation
(display-only) and compute the ``buy_candidate`` boolean (open FGI gate +
idoneous setup + fresh ticker data).

This is a CLASSIFICATION, not a score: it never touches ``attrattiva``,
``compute_signal`` or the FGI gate semantics (technical_setup ≠ final_action
≠ market_gate). ``valuation``/``upside_pct`` never participates in
``setup_type`` or ``buy_candidate`` (``usable_in_strategy_score = false``,
coherent with vix_spot).

Thresholds are config-driven (``config.yaml`` → ``strategy.setup_type``) and
their defaults are aligned to values already encoded in the strategy:
``drawdown >= -5`` (vicino ai massimi, technical_signal/semaforo "ok"),
``RSI < 30`` and ``MFI < 20`` (ipervenduto, technical_signal).
"""

from __future__ import annotations

from typing import Any

# Defaults aligned to thresholds already codified in the strategy.
DEFAULT_SETUP_THRESHOLDS: dict[str, Any] = {
    "drawdown_pullback_pct": -5,  # drawdown < soglia → pullback significativo
    "rsi_oversold": 30,           # RSI < soglia → setup "scarico"
    "mfi_oversold": 20,           # MFI < soglia → setup "scarico"
    "defensive_symbols": [],      # marcato in config.yaml (strategy.setup_type)
}

SETUP_PULLBACK = "PULLBACK_IN_TREND"
SETUP_CONTINUATION = "TREND_CONTINUATION"
SETUP_DEFENSIVE = "INCOME_DEFENSIVE"
SETUP_UNKNOWN = "UNKNOWN"

SETUP_TYPES = (SETUP_PULLBACK, SETUP_CONTINUATION, SETUP_DEFENSIVE, SETUP_UNKNOWN)

# Setups eligible for buy_candidate (UNKNOWN/DEFENSIVE are never eligible).
BUY_CANDIDATE_SETUPS = frozenset({SETUP_PULLBACK, SETUP_CONTINUATION})

# Operational Buy-the-Dip gate: BUY consentito solo con FGI ≤ 25
# (buy_the_dip_gate → "open"/"strong_open").
FGI_BUY_THRESHOLD = 25

# Readable labels for the report table (raw enum kept in data-value/title).
SETUP_LABELS: dict[str, str] = {
    SETUP_PULLBACK: "Pullback in trend",
    SETUP_CONTINUATION: "Continuazione",
    SETUP_DEFENSIVE: "Difensivo",
    SETUP_UNKNOWN: "—",
}


def load_setup_thresholds(config: dict[str, Any] | None) -> dict[str, Any]:
    """Merge ``strategy.setup_type`` from config over the aligned defaults.

    Unknown keys are ignored; a non-list ``defensive_symbols`` falls back to
    the default (fail-closed, never crashes the pipeline).
    """
    thresholds = dict(DEFAULT_SETUP_THRESHOLDS)
    strategy = (config or {}).get("strategy")
    section = strategy.get("setup_type") if isinstance(strategy, dict) else None
    if not isinstance(section, dict):
        return thresholds
    for key in ("drawdown_pullback_pct", "rsi_oversold", "mfi_oversold"):
        value = section.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            thresholds[key] = value
    symbols = section.get("defensive_symbols")
    if isinstance(symbols, list):
        thresholds["defensive_symbols"] = [str(s) for s in symbols]
    return thresholds


def is_defensive(symbol: str, thresholds: dict[str, Any] | None) -> bool:
    """True when the symbol is listed in ``defensive_symbols`` (case-insensitive)."""
    symbols = (thresholds or {}).get("defensive_symbols") or []
    return str(symbol).upper() in {str(s).upper() for s in symbols}


def _is_oversold(entry: dict[str, Any], thresholds: dict[str, Any]) -> bool:
    """RSI/MFI below the configured oversold thresholds (setup "scarico")."""
    rsi = entry.get("rsi_14")
    if rsi is not None and rsi < thresholds["rsi_oversold"]:
        return True
    mfi = entry.get("mfi_14")
    if mfi is not None and mfi < thresholds["mfi_oversold"]:
        return True
    return False


def compute_setup_type(
    entry: dict[str, Any],
    thresholds: dict[str, Any] | None = None,
    *,
    defensive: bool = False,
) -> str:
    """Classify the technical setup of one ticker (fail-closed).

    Rules, in order:

    1. static defensive marker → ``INCOME_DEFENSIVE`` (a label, valid even
       above the SMAs or with missing data — it never yields a buy);
    2. missing price / SMA50 / SMA200 → ``UNKNOWN``;
    3. price below SMA50 or SMA200 → ``UNKNOWN`` (no in-trend setup exists;
       the enum has no bearish value — fail-closed, never a buy);
    4. RSI/MFI oversold OR drawdown below the pullback threshold →
       ``PULLBACK_IN_TREND`` (rientro significativo dai massimi);
    5. drawdown known (≥ threshold) → ``TREND_CONTINUATION`` (vicino ai
       massimi 52w);
    6. drawdown missing and not oversold → ``UNKNOWN``.

    ``valuation``/``upside_pct`` is deliberately NOT consulted (display-only).
    ``thresholds`` is a partial dict merged over ``DEFAULT_SETUP_THRESHOLDS``.
    """
    th = {**DEFAULT_SETUP_THRESHOLDS, **(thresholds or {})}
    if defensive:
        return SETUP_DEFENSIVE
    price = entry.get("last_close")
    sma50 = entry.get("sma_50")
    sma200 = entry.get("sma_200")
    if price is None or sma50 is None or sma200 is None:
        return SETUP_UNKNOWN
    if price < sma50 or price < sma200:
        return SETUP_UNKNOWN
    if _is_oversold(entry, th):
        return SETUP_PULLBACK
    drawdown = entry.get("drawdown_52w")
    if drawdown is None:
        return SETUP_UNKNOWN
    if drawdown < th["drawdown_pullback_pct"]:
        return SETUP_PULLBACK
    return SETUP_CONTINUATION


def compute_value_flag(entry: dict[str, Any]) -> str:
    """Informational valuation note (display-only, never blocking).

    ``"upside > 0"`` when ``upside_pct`` is positive, ``"upside ≤ 0"`` when
    zero/negative, ``"n/d"`` when missing. Never influences ``setup_type``,
    ``buy_candidate`` or ``attrattiva``.
    """
    upside = entry.get("upside_pct")
    if upside is None:
        return "n/d"
    return "upside > 0" if upside > 0 else "upside ≤ 0"


def ticker_is_fresh(entry: dict[str, Any] | None) -> bool:
    """True when the ticker row carries status "fresh" (fail-closed)."""
    return bool(entry) and entry.get("status") == "fresh"


def compute_buy_candidate(
    setup_type: str,
    *,
    fgi_score: float | None,
    fgi_fresh: bool,
    ticker_fresh: bool,
) -> bool:
    """AND of: open FGI gate (≤ 25) + idoneous setup + fresh ticker data.

    ``UNKNOWN`` → False even with an open gate; missing/stale FGI → False
    (fail-closed). ``valuation``/``upside_pct`` is NOT part of the flag.
    """
    if setup_type not in BUY_CANDIDATE_SETUPS:
        return False
    if not ticker_fresh:
        return False
    if not fgi_fresh or fgi_score is None:
        return False
    return fgi_score <= FGI_BUY_THRESHOLD


def buy_candidate_reasons(
    setup_type: str,
    *,
    fgi_score: float | None,
    fgi_fresh: bool,
    ticker_fresh: bool,
) -> list[str]:
    """Human-readable motivations for the buy_candidate flag (Markdown)."""
    if setup_type in BUY_CANDIDATE_SETUPS:
        reasons = [f"setup {setup_type} idoneo all'ingresso"]
    else:
        reasons = [f"setup {setup_type} non idoneo all'ingresso"]
    if fgi_fresh and fgi_score is not None:
        op = "≤" if fgi_score <= FGI_BUY_THRESHOLD else ">"
        state = "aperto" if fgi_score <= FGI_BUY_THRESHOLD else "chiuso"
        reasons.append(f"gate FGI {state}: FGI {fgi_score:.0f} {op} {FGI_BUY_THRESHOLD}")
    else:
        reasons.append("gate FGI non disponibile/fresh (fail-closed)")
    reasons.append(
        "dati ticker freschi" if ticker_fresh else "dati ticker stale/non freschi"
    )
    return reasons


def annotate_output(
    output: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inject ``setup_type`` / ``buy_candidate`` / ``value_flag`` per ticker.

    Writes the classification into the per-ticker dicts of ``output.json``
    (indicators entry when present, else ohlcv) so the artifact carries it.
    The report recomputes the same pure functions at render time (fresh
    thresholds from config); both paths share this module.

    ``valuation`` is consulted only for ``value_flag`` (upside_pct).
    """
    thresholds = load_setup_thresholds(config)
    fgi = output.get("fgi") or {}
    fgi_fresh = fgi.get("status") == "fresh"
    fgi_score = fgi.get("score") if fgi_fresh else None
    indicators = output.get("indicators") or {}
    ohlcv = output.get("ohlcv") or {}
    valuation = output.get("valuation") or {}

    def _categories(mapping: Any) -> set[str]:
        return {k for k, v in mapping.items() if isinstance(v, dict)} if isinstance(mapping, dict) else set()

    for category in sorted(_categories(indicators) | _categories(ohlcv)):
        ind = indicators.get(category) if isinstance(indicators.get(category), dict) else {}
        ohl = ohlcv.get(category) if isinstance(ohlcv.get(category), dict) else {}
        val = valuation.get(category) if isinstance(valuation.get(category), dict) else {}
        symbols = {
            symbol
            for symbol in set(ind) | set(ohl)
            if isinstance(ind.get(symbol), dict) or isinstance(ohl.get(symbol), dict)
        }
        for symbol in symbols:
            ind_entry = ind.get(symbol) if isinstance(ind.get(symbol), dict) else None
            ohl_entry = ohl.get(symbol) if isinstance(ohl.get(symbol), dict) else None
            # Merged view (ohlcv base, indicators win) + valuation overlay
            # for upside_pct only — meta keys never leak into classification.
            entry: dict[str, Any] = dict(ohl_entry or {})
            if ind_entry:
                entry.update(ind_entry)
            val_entry = val.get(symbol) if isinstance(val.get(symbol), dict) else None
            upside = val_entry.get("upside_pct") if val_entry else None
            if upside is not None:
                entry["upside_pct"] = upside

            setup = compute_setup_type(
                entry, thresholds, defensive=is_defensive(symbol, thresholds)
            )
            buy_candidate = compute_buy_candidate(
                setup,
                fgi_score=fgi_score,
                fgi_fresh=fgi_fresh,
                ticker_fresh=ticker_is_fresh(entry),
            )
            target = ind_entry if ind_entry is not None else ohl_entry
            if target is None:
                continue
            target["setup_type"] = setup
            target["buy_candidate"] = buy_candidate
            target["value_flag"] = compute_value_flag(entry)
    return output
