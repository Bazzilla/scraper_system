"""SELL strategy evaluation engine.

Evaluates each open position against configurable rules and produces
an informational sell signal.  Never emits binding orders — only
suggestions for human decision-making.

Thresholds and signal parameters live in ``config/sell_rules.yaml``
and are loaded at call time (config-driven, no hardcoded magic numbers).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class SellEvaluation:
    ticker: str
    sell_signal: str  # one of the 5 states
    confidence: str   # low / medium / high
    reasons: list[str] = field(default_factory=list)
    suggested_action_note: str = ""


# ── Config loading ───────────────────────────────────────────────────────────

_DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "sell_rules.yaml"


def load_rules(path: str | Path | None = None) -> dict[str, Any]:
    """Load sell rules from YAML. Falls back to defaults if path is missing."""
    path = Path(path) if path else _DEFAULT_RULES_PATH
    if not path.exists():
        return {"thresholds": {}, "signals": {}}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# ── Data extraction helpers ──────────────────────────────────────────────────

def _find_ticker_data(
    output: dict[str, Any], ticker: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Find indicators, ohlcv, and valuation data for a ticker across categories.

    Returns (indicators, ohlcv, valuation) — each None if not found.
    """
    indicators = output.get("indicators", {})
    ohlcv = output.get("ohlcv", {})
    valuation = output.get("valuation", {})

    ind_data = None
    ohlcv_data = None
    val_data = None

    for src, store in [
        (indicators, "indicators"),
        (ohlcv, "ohlcv"),
        (valuation, "valuation"),
    ]:
        for category in src.values():
            if not isinstance(category, dict):
                continue
            entry = category.get(ticker)
            if entry is not None and isinstance(entry, dict):
                if store == "indicators":
                    ind_data = entry
                elif store == "ohlcv":
                    ohlcv_data = entry
                elif store == "valuation":
                    val_data = entry

    return ind_data, ohlcv_data, val_data


def _get_fgi_score(output: dict[str, Any]) -> float | None:
    """Extract the FGI score from output.json, or None if unavailable."""
    fgi = output.get("fgi", {})
    if not isinstance(fgi, dict):
        return None
    score = fgi.get("score")
    if score is None:
        return None
    try:
        return float(score)
    except (TypeError, ValueError):
        return None


# ── Overheat / weakness signal detection ─────────────────────────────────────

def _count_overheat_signals(
    fgi: float | None,
    rsi: float | None,
    mfi: float | None,
    last_close: float | None,
    sma50: float | None,
    obv: float | None,
    obv_prev: float | None,
    upside_pct: float | None,
    signals: dict[str, Any],
) -> int:
    """Count how many overheating conditions are active (0–6)."""
    count = 0
    if fgi is not None and fgi >= signals.get("fgi_overheating", 60):
        count += 1
    if rsi is not None and rsi >= signals.get("rsi_overheating", 70):
        count += 1
    if mfi is not None and mfi >= signals.get("mfi_overheating", 80):
        count += 1
    if last_close is not None and sma50 is not None and sma50 > 0:
        pct_above = (last_close / sma50 - 1) * 100
        if pct_above >= signals.get("sma50_overheat_pct", 10):
            count += 1
    # OBV divergence: price rising but OBV falling
    if obv is not None and obv_prev is not None and obv < obv_prev:
        if last_close is not None and sma50 is not None and last_close > sma50:
            count += 1
    if upside_pct is not None and upside_pct <= 5:
        count += 1
    return count


def _count_negative_signals(
    last_close: float | None,
    sma50: float | None,
    sma200: float | None,
    rsi: float | None,
    mfi: float | None,
    obv: float | None,
    obv_prev: float | None,
    signals: dict[str, Any],
) -> int:
    """Count how many negative technical conditions are active (0–5)."""
    count = 0
    if last_close is not None and sma50 is not None and last_close < sma50:
        count += 1
    if last_close is not None and sma200 is not None and last_close < sma200:
        count += 1
    if rsi is not None and rsi < signals.get("rsi_weak", 45):
        count += 1
    if mfi is not None and mfi < signals.get("mfi_weak", 40):
        count += 1
    if obv is not None and obv_prev is not None and obv < obv_prev:
        count += 1
    return count


# ── Main evaluation ──────────────────────────────────────────────────────────

def evaluate_position(
    ticker: str,
    position: dict[str, Any],
    output: dict[str, Any],
    rules: dict[str, Any] | None = None,
) -> SellEvaluation:
    """Evaluate a single open position against the SELL strategy rules.

    Args:
        ticker: the ticker symbol.
        position: dict from portfolio engine (quantity, realized_pnl, etc.).
        output: the full output.json data (indicators, ohlcv, fgi, valuation).
        rules: optional pre-loaded rules dict (re-loaded from YAML if None).

    Returns:
        SellEvaluation with signal, confidence, reasons and action note.
    """
    rules = rules or load_rules()
    thresholds = rules.get("thresholds", {})
    signals = rules.get("signals", {})

    qty = position.get("quantity", 0)
    if qty <= 0:
        return SellEvaluation(
            ticker=ticker,
            sell_signal="NESSUNA POSIZIONE",
            confidence="high",
            reasons=["Nessuna posizione aperta per questo ticker."],
            suggested_action_note="Nessuna azione richiesta.",
        )

    unrealized_pct = position.get("unrealized_pnl_pct")
    ind, ohlcv, val = _find_ticker_data(output, ticker)

    # Extract indicator values (safe defaults if missing).
    rsi = ind.get("rsi_14") if ind else None
    mfi = ind.get("mfi_14") if ind else None
    sma50 = ind.get("sma_50") if ind else None
    sma200 = ind.get("sma_200") if ind else None
    obv = ind.get("obv") if ind else None
    last_close = ohlcv.get("last_close") if ohlcv else None
    upside_pct = val.get("upside_pct") if val else None
    fgi = _get_fgi_score(output)

    reasons: list[str] = []
    confidence = "medium"

    # ── Rule: RIDUCI ESPOSIZIONE (TP3) ───────────────────────────────────
    tp3 = thresholds.get("tp3_pct", 30)
    min_oh = thresholds.get("overheating_min_signals", 2)
    if unrealized_pct is not None and unrealized_pct >= tp3:
        oh_count = _count_overheat_signals(
            fgi, rsi, mfi, last_close, sma50, obv, None, upside_pct, signals,
        )
        if oh_count >= min_oh:
            reasons.append(f"Gain non realizzato {unrealized_pct:.1f}% supera soglia {tp3}%")
            reasons.append(f"Condizioni di surriscaldamento: {oh_count}/{min_oh}+ attive")
            if fgi is not None:
                reasons.append(f"FGI {fgi:.0f} ({'surriscaldato' if fgi >= signals.get('fgi_overheating', 60) else 'ok'})")
            if rsi is not None:
                reasons.append(f"RSI {rsi:.1f} ({'ipercomprato' if rsi >= signals.get('rsi_overheating', 70) else 'ok'})")
            if mfi is not None:
                reasons.append(f"MFI {mfi:.1f} ({'ipercomprato' if mfi >= signals.get('mfi_overheating', 80) else 'ok'})")
            confidence = "high"
            return SellEvaluation(
                ticker=ticker,
                sell_signal="RIDUCI ESPOSIZIONE",
                confidence=confidence,
                reasons=reasons,
                suggested_action_note=(
                    "Valutare riduzione dell'40-50% della posizione. "
                    "Il rischio di ritracciamento è elevato."
                ),
            )

    # ── Rule: PRENDI PROFITTO PARZIALE (TP2 — rafforzato) ────────────────
    tp2 = thresholds.get("tp2_pct", 25)
    if unrealized_pct is not None and unrealized_pct >= tp2:
        reasons.append(f"Gain non realizzato {unrealized_pct:.1f}% supera soglia {tp2}%")
        reasons.append("Rimbalzo Buy-the-Dip con recupero significativo")
        if upside_pct is not None and upside_pct <= 5:
            reasons.append(f"Upside residuo da target analyst basso ({upside_pct:.1f}%)")
            confidence = "high"
        else:
            confidence = "medium"
        return SellEvaluation(
            ticker=ticker,
            sell_signal="PRENDI PROFITTO PARZIALE",
            confidence=confidence,
            reasons=reasons,
            suggested_action_note=(
                "Valutare ulteriore realizzo di circa 25-33% della posizione. "
                "Il gain è maturo per una presa di profitto."
            ),
        )

    # ── Rule: PRENDI PROFITTO PARZIALE (TP1 — base) ──────────────────────
    tp1 = thresholds.get("tp1_pct", 15)
    if unrealized_pct is not None and unrealized_pct >= tp1:
        reasons.append(f"Gain non realizzato {unrealized_pct:.1f}% supera soglia {tp1}%")
        reasons.append("Prima soglia di take profit raggiunta")
        return SellEvaluation(
            ticker=ticker,
            sell_signal="PRENDI PROFITTO PARZIALE",
            confidence="medium",
            reasons=reasons,
            suggested_action_note=(
                "Valutare realizzo di circa 25-33% della posizione. "
                "Mettere in sicurezza parte del guadagno."
            ),
        )

    # ── Rule: ATTENZIONE ──────────────────────────────────────────────────
    min_neg = thresholds.get("attention_min_negative_signals", 2)
    neg_count = _count_negative_signals(
        last_close, sma50, sma200, rsi, mfi, obv, None, signals,
    )
    if unrealized_pct is not None and unrealized_pct <= 0 and neg_count >= min_neg:
        reasons.append(f"Posizione in {'perdita' if unrealized_pct < 0 else 'gain trascurabile'} ({unrealized_pct:.1f}%)")
        reasons.append(f"Condizioni tecniche negative: {neg_count}/{min_neg}+ attive")
        if last_close is not None and sma50 is not None and last_close < sma50:
            reasons.append(f"Prezzo ({last_close:.2f}) sotto SMA50 ({sma50:.2f})")
        if last_close is not None and sma200 is not None and last_close < sma200:
            reasons.append(f"Prezzo ({last_close:.2f}) sotto SMA200 ({sma200:.2f})")
        if rsi is not None and rsi < signals.get("rsi_weak", 45):
            reasons.append(f"RSI {rsi:.1f} debole")
        if mfi is not None and mfi < signals.get("mfi_weak", 40):
            reasons.append(f"MFI {mfi:.1f} debole")
        return SellEvaluation(
            ticker=ticker,
            sell_signal="ATTENZIONE",
            confidence="medium",
            reasons=reasons,
            suggested_action_note=(
                "Monitorare attentamente. Il deterioramento potrebbe essere "
                "temporaneo o strutturale. Non generare automaticamente un'uscita."
            ),
        )

    # ── Rule: MANTIENI (default when in gain and healthy) ─────────────────
    reasons.append("Trend e volumi restano sani")
    if unrealized_pct is not None and unrealized_pct > 0:
        reasons.append(f"Gain non realizzato {unrealized_pct:.1f}%")
    if rsi is not None:
        reasons.append(f"RSI {rsi:.1f} in range normale")
    return SellEvaluation(
        ticker=ticker,
        sell_signal="MANTIENI",
        confidence="high",
        reasons=reasons,
        suggested_action_note="Posizione sana, nessuna azione necessaria.",
    )


def evaluate_all(
    positions: list[dict[str, Any]],
    output: dict[str, Any],
    rules: dict[str, Any] | None = None,
) -> list[SellEvaluation]:
    """Evaluate SELL signals for all open positions.

    Args:
        positions: list of position dicts from the portfolio engine.
        output: the full output.json data.
        rules: optional pre-loaded rules dict.

    Returns:
        List of SellEvaluation, one per position.
    """
    rules = rules or load_rules()
    return [
        evaluate_position(pos["ticker"], pos, output, rules=rules)
        for pos in positions
    ]
