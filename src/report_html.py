"""Static HTML report generator.

Reads the consolidated output.json produced by the orchestrator and renders a
self-contained HTML page (dark theme with light toggle) showing market
indicators, per-sector ticker tables with technical indicators and semaphores,
and last-update timestamps.

Standalone script: ``render(config_path)`` — not wired into the orchestrator.

REMINDER: when a new scraper/module is added, update this module so the report
renders it too (see README "Report HTML statico").

This module is now an orchestrator: the rendering logic has been split into
``report_helpers`` (shared helpers/constants), ``report_cards`` (market cards),
``report_tables`` (ticker tables, indicator matrix, stale summary) and
``report_legend`` (legend + guide). Everything is re-exported here so existing
imports (tests, overrides_page, overrides_server) keep working unchanged.
"""

from __future__ import annotations

import html as html_mod
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from config_loader import normalize_tickers

# Re-export from submodules so existing imports (tests, overrides_page,
# overrides_server) keep working unchanged.
from report_helpers import (  # noqa: F401
    _FGI_ZONES,
    _ITALIAN_MONTHS,
    _age_attrs,
    _badge,
    _collapsible,
    _fgi_rating_badge,
    _now_iso,
    _sema,
    _signal_badge,
    _status_badge,
    buy_the_dip_gate,
    compute_signal,
    final_action,
    fmt,
    format_iso_dt,
    market_regime,
    render_nav,
    semaphore_class,
    technical_signal,
)
from report_helpers import FAVICON_LINK  # noqa: F401
from report_cards import render_market_cards  # noqa: F401
from report_legend import render_legend  # noqa: F401
from report_tables import (  # noqa: F401
    _ticker_sections,
    render_indicator_matrix,
    render_stale_summary,
    render_ticker_table,
)

DEFAULT_HTML_PATH = "output/report.html"

_CSS = """\
:root { --bg: #0f1419; --card: #1a212b; --border: #2c3542; --text: #e6edf3;
        --muted: #8b949e; --green: #2ea043; --yellow: #d29922; --red: #f85149;
        --neutral: #58a6ff; }
[data-theme="light"] { --bg: #f6f8fa; --card: #ffffff; --border: #d0d7de;
        --text: #1f2328; --muted: #57606a; --green: #1a7f37; --yellow: #9a6700;
        --red: #cf222e; --neutral: #0969da; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        sans-serif; background: var(--bg); color: var(--text); line-height: 1.5;
        padding: 24px; }
.container { max-width: 1100px; margin: 0 auto; }
header { display: flex; justify-content: space-between; align-items: center;
        flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }
h1 { font-size: 1.5rem; }
.sub { color: var(--muted); font-size: 0.9rem; }
.badge { padding: 2px 10px; border-radius: 999px; font-size: 0.8rem;
        font-weight: 600; }
.badge.fresh { background: var(--green); color: #fff; }
.badge.stale { background: var(--red); color: #fff; }
.age { color: var(--muted); font-size: 0.75rem; display: block; margin-top: 2px; }
.badge.age-badge { margin-left: 8px; }
.fgi-components { margin-top: 10px; border-top: 1px solid var(--border);
        padding-top: 8px; display: grid; gap: 4px; font-size: 0.8rem; }
.fgi-components .comp { display: flex; justify-content: space-between;
        align-items: center; gap: 8px; }
.fgi-components .comp-name { color: var(--muted); }
button#theme-toggle { background: var(--card); color: var(--text);
        border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px;
        cursor: pointer; font-size: 0.9rem; }
h2 { margin: 28px 0 12px; font-size: 1.15rem; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 16px; }
.card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 16px; }
.card .label { color: var(--muted); font-size: 0.8rem; text-transform: uppercase;
        letter-spacing: 0.05em; }
.card .value { font-size: 1.6rem; font-weight: 700; margin: 4px 0; }
.card .meta { color: var(--muted); font-size: 0.8rem; }
.sema { display: inline-block; padding: 1px 8px; border-radius: 6px;
        font-size: 0.75rem; font-weight: 600; }
.sema.overbought { background: var(--red); color: #fff; }
.sema.oversold { background: var(--green); color: #fff; }
.sema.warning { background: var(--yellow); color: #1f2328; }
.sema.critical { background: var(--red); color: #fff; }
.sema.ok { background: var(--green); color: #fff; }
.sema.neutral { background: var(--card); border: 1px solid var(--border);
        color: var(--neutral); }
.sema.fear { background: var(--red); color: #fff; }
.sema.greed { background: var(--green); color: #fff; }
.sema.extreme_fear { background: var(--red); color: #fff; }
.sema.extreme_greed { background: var(--green); color: #fff; }
.sema-cell { display: flex; justify-content: space-between; align-items: center;
        gap: 8px; width: 100%; }
.sema-val { white-space: nowrap; }
table { width: 100%; border-collapse: collapse; background: var(--card);
        border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
th, td { padding: 8px 12px; text-align: right; border-bottom: 1px solid var(--border);
        font-size: 0.9rem; }
th { background: var(--card); color: var(--muted); font-weight: 600;
        text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.04em;
        text-align: center; }
td:first-child, th:first-child { text-align: left; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(88, 166, 255, 0.06); }
.ticker { font-weight: 700; }
.name { color: var(--muted); font-size: 0.8rem; }
.ticker-meta { display: block; color: var(--muted); font-size: 0.72rem;
        line-height: 1.4; margin-top: 2px; }
.meta-tier { color: var(--accent); font-weight: 600; }
.meta-validity { color: var(--muted); }
.meta-role { color: var(--muted); font-style: italic; }
.meta-notes { color: var(--muted); opacity: 0.85; }
footer { margin-top: 32px; color: var(--muted); font-size: 0.85rem;
        border-top: 1px solid var(--border); padding-top: 16px; }
.legend { margin-top: 24px; }
.legend-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
        gap: 12px; }
.legend-card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 12px 16px; }
.legend-card summary { cursor: pointer; font-weight: 600; font-size: 0.9rem;
        display: flex; justify-content: space-between; align-items: center;
        gap: 8px; list-style: none; }
.legend-card summary::-webkit-details-marker { display: none; }
.legend-card summary::after { content: "ℹ️"; font-size: 0.9rem; }
.legend-card[open] summary::after { content: "✖"; font-size: 0.9rem; }
.legend-card .legend-detail { margin-top: 8px; color: var(--text); font-size: 0.85rem;
        border-top: 1px solid var(--border); padding-top: 8px; }
.legend-card .legend-range { color: var(--muted); font-size: 0.8rem; }
.guide { margin-top: 24px; background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 16px; }
.guide h3 { font-size: 1rem; margin-bottom: 8px; }
.guide ul { padding-left: 20px; }
.guide li { margin: 6px 0; }
.sema-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
        margin-right: 6px; vertical-align: middle; }
.sema-dot.ok, .sema-dot.oversold { background: var(--green); }
.sema-dot.warning { background: var(--yellow); }
.sema-dot.critical, .sema-dot.overbought { background: var(--red); }
.sema-dot.neutral { background: var(--neutral); }
.signal { display: inline-block; padding: 2px 10px; border-radius: 6px;
        font-size: 0.78rem; font-weight: 700; white-space: nowrap; }
.signal.buy { background: var(--green); color: #fff; }
.signal.watchlist { background: var(--yellow); color: #1f2328; }
.signal.hold { background: var(--card); border: 1px solid var(--border);
        color: var(--neutral); }
.indicator-matrix { margin-top: 24px; }
.indicator-matrix table { width: 100%; }
.indicator-matrix td { text-align: left; vertical-align: top; }
.indicator-matrix th { text-align: left; }
details.section { margin: 28px 0 12px; background: var(--card);
        border: 1px solid var(--border); border-radius: 12px; }
details.section > summary { cursor: pointer; list-style: none; padding: 12px 16px;
        display: flex; align-items: center; justify-content: space-between; }
details.section > summary::-webkit-details-marker { display: none; }
details.section > summary h2 { margin: 0; font-size: 1.15rem; }
details.section > summary::after { content: "▾"; font-size: 1rem; color: var(--muted);
        transition: transform 0.15s ease; }
details.section[open] > summary::after { transform: rotate(180deg); }
details.section > .section-body { padding: 0 16px 16px; }
button#sections-toggle { background: var(--card); color: var(--text);
        border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px;
        cursor: pointer; font-size: 0.9rem; }
.sections-toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.page-nav { display: inline-flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.page-nav a { padding: 4px 12px; border-radius: 999px; font-size: 0.85rem;
        font-weight: 600; text-decoration: none; background: var(--card);
        color: var(--text); border: 1px solid var(--border); }
.page-nav a.active { background: var(--green); color: #fff;
        border-color: var(--green); }
.page-nav a:hover { opacity: 0.85; }
/* Sort & filter tabelle ticker */
table.ticker-table th.sortable { cursor: pointer; user-select: none; }
table.ticker-table th.sorted { color: var(--neutral); }
.filter-row td { padding: 4px 6px; background: var(--bg); }
.filter-row input, .filter-row select { width: 100%; min-width: 70px;
        background: var(--card); color: var(--text);
        border: 1px solid var(--border); border-radius: 6px;
        padding: 4px 6px; font-size: 0.78rem; box-sizing: border-box; }
.num-filter { display: flex; gap: 4px; }
.num-filter select { width: auto; flex: 0 0 auto; }
.table-tools { display: flex; justify-content: flex-end; margin-bottom: 6px; }
.table-reset { background: var(--card); color: var(--text);
        border: 1px solid var(--border); border-radius: 8px;
        padding: 4px 10px; cursor: pointer; font-size: 0.8rem; }
.table-reset:hover { opacity: 0.85; }
.legend-strategy { margin-top: 8px; font-size: 0.85rem;
        background: rgba(88, 166, 255, 0.08);
        border-left: 3px solid var(--neutral); padding: 6px 10px;
        border-radius: 6px; }
"""

_SCRIPT = """\
<script>
(function () {
  var saved = localStorage.getItem("report-theme");
  var theme = saved || "dark";
  document.documentElement.setAttribute("data-theme", theme);
  var btn = document.getElementById("theme-toggle");
  btn.textContent = theme === "dark" ? "☀️ Light" : "🌙 Dark";
  btn.addEventListener("click", function () {
    var next = theme === "dark" ? "light" : "dark";
    theme = next;
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("report-theme", next);
    btn.textContent = next === "dark" ? "☀️ Light" : "🌙 Dark";
  });

  function fmtAge(ms) {
    var min = Math.floor(ms / 60000);
    if (min < 60) return min + "min fa";
    var h = Math.floor(min / 60);
    if (h < 24) return h + "h fa";
    return Math.floor(h / 24) + "g fa";
  }

  function fmtRemaining(ms) {
    var min = Math.ceil(ms / 60000);
    if (min < 60) return "tra " + min + "min";
    var h = Math.ceil(min / 60);
    if (h < 24) return "tra " + h + "h";
    return "tra " + Math.ceil(h / 24) + "g";
  }

  var els = document.querySelectorAll("[data-fetched-at]");
  for (var i = 0; i < els.length; i++) {
    var el = els[i];
    var fetched = Date.parse(el.getAttribute("data-fetched-at"));
    if (isNaN(fetched)) continue;
    var staleHours = parseFloat(el.getAttribute("data-stale-hours")) || 0;
    var ageMs = Date.now() - fetched;
    if (ageMs < 0) ageMs = 0;
    var staleMs = staleHours * 3600000;
    var isStale = ageMs > staleMs;
    var status = isStale ? "stale" : "fresh";
    var text = isStale
      ? "scaduto da " + fmtAge(ageMs - staleMs)
      : "aggiornato " + fmtAge(ageMs) + " · " + fmtRemaining(staleMs - ageMs);

    var badge = document.createElement("span");
    badge.className = "badge age-badge " + status;
    badge.textContent = status;
    var value = el.querySelector(".value");
    if (value) {
      value.parentNode.insertBefore(badge, value.nextSibling);
    } else {
      var firstCell = el.querySelector("td:first-child");
      if (firstCell) firstCell.appendChild(badge);
    }

    var age = document.createElement("span");
    age.className = "age";
    age.textContent = text;
    var metas = el.querySelectorAll(".meta");
    var meta = metas.length ? metas[metas.length - 1] : null;
    if (meta) {
      meta.appendChild(age);
    } else {
      var lastCell = el.querySelector("td:last-child");
      if (lastCell) lastCell.appendChild(age);
    }
  }

  // Collapsible sections: global "Apri tutte / Chiudi tutte" toggle.
  var sections = document.querySelectorAll("details.section");
  var sectionsBtn = document.getElementById("sections-toggle");
  function allOpen() {
    for (var i = 0; i < sections.length; i++) {
      if (!sections[i].open) return false;
    }
    return true;
  }
  function updateSectionsLabel() {
    if (sectionsBtn) {
      sectionsBtn.textContent = allOpen() ? "🗂️ Chiudi tutte" : "🗂️ Apri tutte";
    }
  }
  if (sectionsBtn) {
    sectionsBtn.addEventListener("click", function () {
      var open = !allOpen();
      for (var i = 0; i < sections.length; i++) {
        sections[i].open = open;
      }
      updateSectionsLabel();
    });
    for (var i = 0; i < sections.length; i++) {
      sections[i].addEventListener("toggle", updateSectionsLabel);
    }
    updateSectionsLabel();
  }
})();
</script>
"""


_TABLE_SCRIPT = """\
<script>
// --- Sort & filter per le tabelle ticker -------------------------------
// Sort ciclico per colonna: click → asc, click → desc, click → nessuno.
// Un solo ordinamento alla volta. Filtri: testo (contiene), numerici con
// operatori (> ≥ = ≤ <) e date semantiche (oggi/ieri/ultimi 7gg/più vecchio).
(function () {
  var NUM_OPS = [">", "≥", "=", "≤", "<"];
  var DATE_OPTS = [
    ["", "(qualsiasi data)"],
    ["today", "oggi"],
    ["yesterday", "ieri"],
    ["7d", "ultimi 7 giorni"],
    ["older", "più vecchio di 7 giorni"]
  ];

  function cellValue(row, idx, type) {
    var td = row.cells[idx];
    var dv = td.getAttribute("data-value");
    if (type === "num") {
      var src = dv !== null && dv !== "" ? dv : td.textContent.replace(",", ".");
      var n = parseFloat(src);
      return isNaN(n) ? null : n;
    }
    if (type === "date") {
      var t = Date.parse(dv !== null && dv !== "" ? dv : td.textContent);
      return isNaN(t) ? null : t;
    }
    return ((dv || "") + " " + td.textContent).toLowerCase();
  }

  function startOfToday() {
    var now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  }

  function passes(row, headCells, filters) {
    for (var idx = 0; idx < headCells.length; idx++) {
      var f = filters[idx] && filters[idx]();
      if (!f) continue;
      var type = headCells[idx].getAttribute("data-type") || "text";
      var val = cellValue(row, idx, type);
      if (type === "num") {
        if (val === null) return false;
        if (f.op === ">" && !(val > f.num)) return false;
        if (f.op === "≥" && !(val >= f.num)) return false;
        if (f.op === "=" && !(val === f.num)) return false;
        if (f.op === "≤" && !(val <= f.num)) return false;
        if (f.op === "<" && !(val < f.num)) return false;
      } else if (type === "date") {
        if (val === null) return false;
        var s0 = startOfToday(), day = 86400000;
        if (f === "today" && val < s0) return false;
        if (f === "yesterday" && !(val >= s0 - day && val < s0)) return false;
        if (f === "7d" && val < s0 - 7 * day) return false;
        if (f === "older" && val >= s0 - 7 * day) return false;
      } else {
        if (val.indexOf(f) === -1) return false;
      }
    }
    return true;
  }

  function setupTable(table) {
    var thead = table.tHead;
    var headCells = thead.rows[0].cells;
    var tbody = table.tBodies[0];
    var dataRows = Array.prototype.slice.call(tbody.rows);
    var sortCol = -1, sortDir = 0;   // 0 = nessun ordinamento
    dataRows.forEach(function (r, i) { r.setAttribute("data-orig-index", i); });

    // Toolbar con reset (filtri + ordinamento)
    var tools = document.createElement("div");
    tools.className = "table-tools";
    var resetBtn = document.createElement("button");
    resetBtn.type = "button";
    resetBtn.className = "table-reset";
    resetBtn.textContent = "↺ Azzera filtri e ordine";
    tools.appendChild(resetBtn);
    table.parentNode.insertBefore(tools, table);

    // Riga filtri sotto l'intestazione
    var filterRow = thead.insertRow(1);
    filterRow.className = "filter-row";
    var filters = [];

    Array.prototype.forEach.call(headCells, function (th, idx) {
      var type = th.getAttribute("data-type") || "text";
      var cell = filterRow.insertCell(idx);
      cell.className = "filter-cell";
      if (type === "num") {
        var wrap = document.createElement("div");
        wrap.className = "num-filter";
        var sel = document.createElement("select");
        NUM_OPS.forEach(function (op) {
          var o = document.createElement("option");
          o.value = op; o.textContent = op; sel.appendChild(o);
        });
        var inp = document.createElement("input");
        inp.type = "text"; inp.inputMode = "decimal"; inp.placeholder = "valore";
        wrap.appendChild(sel); wrap.appendChild(inp);
        cell.appendChild(wrap);
        filters[idx] = function () {
          var v = inp.value.trim().replace(",", ".");
          return v ? { op: sel.value, num: parseFloat(v) } : null;
        };
        inp.addEventListener("input", apply);
        sel.addEventListener("change", apply);
      } else if (type === "date") {
        var selD = document.createElement("select");
        DATE_OPTS.forEach(function (pair) {
          var o = document.createElement("option");
          o.value = pair[0]; o.textContent = pair[1]; selD.appendChild(o);
        });
        cell.appendChild(selD);
        filters[idx] = function () { return selD.value || null; };
        selD.addEventListener("change", apply);
      } else {
        var inpT = document.createElement("input");
        inpT.type = "text"; inpT.placeholder = "contiene…";
        cell.appendChild(inpT);
        filters[idx] = function () { return inpT.value.trim().toLowerCase() || null; };
        inpT.addEventListener("input", apply);
      }
    });

    // Ordinamento ciclico: asc → desc → nessuno (un solo sort alla volta)
    Array.prototype.forEach.call(headCells, function (th, idx) {
      th.classList.add("sortable");
      th.title = "Clicca: ordina ↑ / ↓ / ripristina";
      var ind = document.createElement("span");
      ind.className = "sort-ind";
      th.appendChild(ind);
      th.addEventListener("click", function () {
        if (sortCol !== idx) { sortCol = idx; sortDir = 1; }
        else if (sortDir === 1) { sortDir = -1; }
        else { sortCol = -1; sortDir = 0; }
        updateIndicators();
        apply();
      });
    });

    function updateIndicators() {
      Array.prototype.forEach.call(headCells, function (th, idx) {
        th.querySelector(".sort-ind").textContent =
          idx === sortCol && sortDir !== 0 ? (sortDir === 1 ? " ▲" : " ▼") : "";
        th.classList.toggle("sorted", idx === sortCol && sortDir !== 0);
      });
    }

    function apply() {
      var visible = [];
      dataRows.forEach(function (row) {
        var ok = passes(row, headCells, filters);
        row.style.display = ok ? "" : "none";
        if (ok) visible.push(row);
      });
      if (sortCol >= 0 && sortDir !== 0) {
        var type = headCells[sortCol].getAttribute("data-type") || "text";
        visible.sort(function (a, b) {
          var va = cellValue(a, sortCol, type), vb = cellValue(b, sortCol, type);
          if (va === null && vb === null) return 0;
          if (va === null) return 1;   // valori mancanti sempre in fondo
          if (vb === null) return -1;
          var cmp = (type === "text")
            ? va.localeCompare(vb)
            : (va < vb ? -1 : va > vb ? 1 : 0);
          return cmp * sortDir;
        });
      } else {
        visible.sort(function (a, b) {
          return (+a.getAttribute("data-orig-index")) - (+b.getAttribute("data-orig-index"));
        });
      }
      visible.forEach(function (row) { tbody.appendChild(row); });
    }

    resetBtn.addEventListener("click", function () {
      sortCol = -1; sortDir = 0;
      updateIndicators();
      filterRow.querySelectorAll("input").forEach(function (i) { i.value = ""; });
      filterRow.querySelectorAll("select").forEach(function (s) { s.selectedIndex = 0; });
      apply();
    });
  }

  document.querySelectorAll("table.ticker-table").forEach(setupTable);
})();
</script>
"""

def build_page(data: dict[str, Any], tickers_config: dict[str, Any] | None = None) -> str:
    """Assemble the complete HTML document.

    ``tickers_config`` (optional) is the normalized ``tickers`` section from
    config.yaml; used only for display metadata and tier ordering.
    """
    stale = data.get("stale_summary", {})
    overall = "fresh" if stale.get("stale", 0) == 0 else "stale"
    title = "Market Dashboard"
    html_doc = (
        "<!DOCTYPE html>\n<html lang=\"it\" data-theme=\"dark\">\n<head>"
        "<meta charset=\"utf-8\">"
        f"{FAVICON_LINK}"
        f"<title>{title}</title>"
        f"<style>{_CSS}</style>"
        "</head>\n<body><div class=\"container\">"
        "<header>"
        f"<div><h1>📊 {title}</h1>"
        f'<div class="sub">Generato: {format_iso_dt(data.get("generated_at"))}</div></div>'
        f'<div><span class="badge {overall}">{overall}</span> '
        f'{render_nav("report")} '
        '<button id="theme-toggle" type="button">☀️ Light</button></div>'
        "</header>"
        '<div class="sections-toolbar">'
        '<button id="sections-toggle" type="button">🗂️ Chiudi tutte</button>'
        "</div>"
        f"{_collapsible('Indicatori di mercato', render_market_cards(data))}"
        f"{_ticker_sections(data, tickers_config)}"
        f"{render_indicator_matrix(data.get('strategy_indicators', {}))}"
        f"{render_stale_summary(stale)}"
        f"{render_legend()}"
        "</div>"
        f"{_SCRIPT}{_TABLE_SCRIPT}"
        "</body>\n</html>"
    )
    return html_doc


def render(config_path: str, output_path: str | None = None) -> str:
    """Render the HTML report from the consolidated output.json.

    Args:
        config_path: Path to config.yaml (used to resolve output.json_path).
        output_path: Where to write the HTML. Defaults to ``output/report.html``
            relative to the config file's directory.

    Returns:
        The path of the generated HTML file.

    Raises:
        FileNotFoundError: If the output JSON does not exist.
    """
    with open(config_path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    base_dir = Path(config_path).resolve().parent
    output_cfg = config.get("output", {})
    json_path = base_dir / output_cfg.get("json_path", "output/output.json")

    if not json_path.exists():
        raise FileNotFoundError(
            f"Output JSON not found at {json_path}. Run the orchestrator first."
        )

    with json_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    # Normalizza la sezione tickers (lista semplice → metadata arricchiti)
    # per il rendering dei metadata strategici nel report (display-only).
    tickers_config = normalize_tickers(config["tickers"]) if "tickers" in config else None

    html_path = output_path or str(base_dir / DEFAULT_HTML_PATH)
    path = Path(html_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_page(data, tickers_config), encoding="utf-8")
    return str(path)
