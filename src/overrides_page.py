"""Manual overrides entry page generator.

Builds a static HTML page (dark/light theme, same styles as the dashboard)
that lets the user edit the manual overrides supported by
``manual_overrides.yaml`` and submit them to the local server
(``overrides_server.py``) which persists them and re-renders the report.

The page is server-rendered by ``GET /`` from the overrides server (values
are pre-filled from ``manual_overrides.yaml``); the JS posts edits to
``POST /api/save``. The ``GET /api/data`` endpoint exists on the server for
debugging/verification but is not consumed by this page.
"""

from __future__ import annotations

import html as html_mod
from typing import Any

from report_html import _CSS, _SCRIPT, format_iso_dt
from report_helpers import render_nav
from indicator_fields import INDICATOR_FIELDS

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
// POST JSON con retry su 401: al primo 401 il browser mostra il prompt di
// Basic Auth e memorizza le credenziali; la richiesta originale NON viene
// ritentata automaticamente, quindi ritentiamo qui (max 2 tentativi).
function postJSON(url, payload, attempt) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }).then(function (resp) {
    if (resp.status === 401 && attempt < 2) return postJSON(url, payload, attempt + 1);
    return resp.json();
  });
}
function saveOverride(key) {
  var card = document.querySelector('[data-key="' + key + '"]');
  var payload = { key: key, enabled: card.querySelector('[name="enabled"]').checked };
  card.querySelectorAll("input[name]").forEach(function (input) {
    if (input.name !== "enabled") payload[input.name] = input.value;
  });
  postJSON("/api/save", payload, 1).then(function (data) {
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
        for indicator, spec in INDICATOR_FIELDS.items()
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
        f'<div>{render_nav("overrides")} '
        '<button id="theme-toggle" type="button">☀️ Light</button></div>'
        "</header>"
        f'<div class="override-form">{cards}</div>'
        "</div>"
        f"{_OVERRIDES_SCRIPT}"
        "</body>\n</html>"
    )
