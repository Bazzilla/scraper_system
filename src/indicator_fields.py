"""Single source of truth for the manual-override indicator descriptors.

Consumed by manual_overrides.py (validation/build), overrides_page.py
(rendering) and overrides_server.py (whitelist + field types). Adding a new
manual-override indicator is a single edit here.
"""

from __future__ import annotations

from typing import Any

# Per-indicator descriptor:
#   label       — display name (page)
#   badge       — "manual" | "fallback" (page)
#   frequency   — output frequency (manual_overrides build)
#   fields      — {field: {"label", "type", "step"}} (page + server validation)
#   required    — list of required value fields (manual_overrides validation)
INDICATOR_FIELDS: dict[str, dict[str, Any]] = {
    "aaii": {
        "label": "AAII Investor Sentiment Survey",
        "badge": "fallback",
        "frequency": "weekly",
        "fields": {
            "bullish": {"label": "Bullish %", "type": "number", "step": "0.1"},
            "neutral": {"label": "Neutral %", "type": "number", "step": "0.1"},
            "bearish": {"label": "Bearish %", "type": "number", "step": "0.1"},
        },
        "required": ["bullish", "neutral", "bearish"],
    },
    "fgi": {
        "label": "Fear & Greed Index",
        "badge": "fallback",
        "frequency": "daily",
        "fields": {
            "score": {"label": "Score (0-100)", "type": "number", "step": "0.1"},
            "zone": {"label": "Zone", "type": "text", "step": None},
        },
        "required": ["score"],
    },
    "naaim": {
        "label": "NAAIM Exposure Index",
        "badge": "manual",
        "frequency": "weekly",
        "fields": {
            "exposure": {"label": "Exposure", "type": "number", "step": "0.1"},
        },
        "required": ["exposure"],
    },
    "vix_term_structure": {
        "label": "VIX Term Structure",
        "badge": "manual",
        "frequency": "daily",
        "fields": {
            "m1": {"label": "M1 (futures 1 mese)", "type": "number", "step": "0.01"},
            "m2": {"label": "M2 (futures 2 mesi)", "type": "number", "step": "0.01"},
        },
        "required": ["m1", "m2"],
    },
    "pct_sma": {
        "label": "% sopra SMA50/SMA200 (mercato USA)",
        "badge": "manual",
        "frequency": "daily",
        "fields": {
            "pct_sma50": {"label": "% sopra SMA50", "type": "number", "step": "0.1"},
            "pct_sma200": {"label": "% sopra SMA200", "type": "number", "step": "0.1"},
        },
        "required": ["pct_sma50", "pct_sma200"],
    },
}

SUPPORTED_KEYS = frozenset(INDICATOR_FIELDS)
