"""Manual overrides entry page generator.

Builds a static HTML page (dark/light theme, same styles as the dashboard)
that lets the user edit the manual overrides supported by
``manual_overrides.yaml`` and submit them to the local server
(``overrides_server.py``) which persists them and re-renders the report.

The page is served by ``GET /`` from the overrides server; it fetches the
current values from ``GET /api/data`` and posts edits to ``POST /api/save``.
"""

from __future__ import annotations

import html as html_mod
from typing import Any

from report_html import _CSS, _SCRIPT, format_iso_dt

# Field descriptors per supported indicator: label, input type, step.
_INDICATOR_FIELDS: dict[str, dict[str, Any]] = {
    "aaii": {
        "label": "AAII Investor Sentiment Survey",
        "badge": "fallback",
        "fields": {
            "bullish": {"label": "Bullish %", "type": "number", "step": "0.1"},
            "neutral": {"label": "Neutral %", "type": "number", "step": "0.1"},
            "bearish": {"label": "Bearish %", "type": "number", "step": "0.1"},
        },
    },
    "fgi": {
        "label": "Fear & Greed Index",
        "badge": "fallback",
        "fields": {
            "score": {"label": "Score (0-100)", "type": "number", "step": "0.1"},
            "zone": {"label": "Zone", "type": "text", "step": None},
        },
    },
    "naaim": {
        "label": "NAAIM Exposure Index",
        "badge": "manual",
        "fields": {
            "exposure": {"label": "Exposure", "type": "number", "step": "0.1"},
        },
    },
    "vix_term_structure": {
        "label": "VIX Term Structure",
        "badge": "manual",
        "fields": {
            "m1": {"label": "M1 (futures 1 mese)", "type": "number", "step": "0.01"},
            "m2": {"label": "M2 (futures 2 mesi)", "type": "number", "step": "0.01"},
        },
    },
    "pct_sma": {
        "label": "% sopra SMA50/SMA200 (mercato USA)",
        "badge": "manual",
        "fields": {
            "pct_sma50": {"label": "% sopra SMA50", "type": "number", "step": "0.1"},
            "pct_sma200": {"label": "% sopra SMA200", "type": "number", "step": "0.1"},
        },
    },
}

_PAGE_CSS = _CSS + """\
.override-form { margin-top: 24px; }
.override-card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 16px; margin-bottom: 16px; }
.override-card .row { display: flex; align-items: center; gap: 12px;
        flex-wrap: wrap; margin-bottom: 8px; }
.override-card label { color: var(--muted); font-size: 0.85rem; }
.override-card input[type="number"], .override-card input[type="text"] {
        background: var(--bg); color: var(--text); border: 1px solid var(--border);
        border-radius: 6px; padding: 6px 8px; font-size: 0.9rem; width: 140px; }
.override-card input[type="text"] { width: 220px; }
.override-card button { background: var(--green); color: #fff; border: none;
        border-radius: 8px; padding: 8px 16px; cursor: pointer; font-size: 0.9rem;
        font-weight: 600; }
.override-card button:hover { opacity: 0.9; }
.msg { padding: 8px 12px; border-radius: 8px; margin: 8px 0; font-size: 0.9rem; }
.msg.ok { background: var(--green); color: #fff; }
.msg.err { background: var(--red); color: #fff; }
"""


def _render_field(key: str, spec: dict[str, Any], value: Any) -> str:
    ftype = spec["type"]
    step = spec.get("step")
    step_attr = f' step="{step}"' if step else ""
    val = "" if value is None else str(value)
    return (
        f'<label>{html_mod.escape(spec["label"])}'
        f'<input type="{ftype}" name="{key}" value="{html_mod.escape(val)}"{step_attr}></label>'
    )


def _render_card(indicator: str, spec: dict[str, Any], entry: dict[str, Any]) -> str:
    enabled = bool(entry.get("enabled", True))
    checked = " checked" if enabled else ""
    fields_html = "".join(
        _render_field(key, fspec, entry.get(key))
        for key, fspec in spec["fields"].items()
    )
    stale = entry.get("stale_after_hours", 24)
    note = entry.get("note", "")
    fetched = format_iso_dt(entry.get("fetched_at"))
    badge_cls = "ok" if spec["badge"] == "manual" else "warning"
    return (
        f'<div class="override-card" data-key="{indicator}">'
        f'<div class="row"><strong>{html_mod.escape(spec["label"])}</strong>'
        f' <span class="sema {badge_cls}">{spec["badge"]}</span>'
        f'<label><input type="checkbox" name="enabled"{checked}> abilitato</label></div>'
        f'<div class="row">{fields_html}</div>'
        f'<div class="row"><label>Validità (h) '
        f'<input type="number" name="stale_after_hours" value="{stale}" step="1"></label>'
        f'<label>Nota <input type="text" name="note" value="{html_mod.escape(str(note))}"></label></div>'
        f'<div class="row"><span class="name">Ultimo: {fetched}</span>'
        f'<button type="button" onclick="saveOverride(\'{indicator}\')">WRITE</button></div>'
        f"</div>"
    )


_OVERRIDES_SCRIPT = _SCRIPT + """\
<script>
function saveOverride(key) {
  var card = document.querySelector('[data-key="' + key + '"]');
  var payload = { key: key, enabled: card.querySelector('[name="enabled"]').checked };
  card.querySelectorAll("input[name]").forEach(function (input) {
    if (input.name !== "enabled") payload[input.name] = input.value;
  });
  fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }).then(function (resp) { return resp.json(); }).then(function (data) {
    var msg = document.createElement("div");
    msg.className = "msg " + (data.ok ? "ok" : "err");
    msg.textContent = data.message || (data.ok ? "Salvato" : "Errore");
    card.appendChild(msg);
    setTimeout(function () { msg.remove(); }, 3000);
  });
}
</script>
"""


def render_overrides_page(overrides: dict[str, Any]) -> str:
    """Render the complete overrides entry page."""
    cards = "".join(
        _render_card(indicator, spec, overrides.get(indicator, {}))
        for indicator, spec in _INDICATOR_FIELDS.items()
    )
    return (
        "<!DOCTYPE html>\n<html lang=\"it\" data-theme=\"dark\">\n<head>"
        "<meta charset=\"utf-8\">"
        "<title>Immissione manuale indicatori</title>"
        f"<style>{_PAGE_CSS}</style>"
        "</head>\n<body><div class=\"container\">"
        "<header>"
        "<div><h1>✍️ Immissione manuale indicatori</h1>"
        '<div class="sub">Valori per gli indicatori non scrapabili</div></div>'
        '<div><a href="/report.html" class="badge fresh">Vai al report →</a> '
        '<button id="theme-toggle" type="button">☀️ Light</button></div>'
        "</header>"
        f'<div class="override-form">{cards}</div>'
        "</div>"
        f"{_OVERRIDES_SCRIPT}"
        "</body>\n</html>"
    )
