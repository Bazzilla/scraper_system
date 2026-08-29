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
from page_base import _BASE_CSS, _SHARED_SCRIPT, render_header, wrap_page

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

"""Report-specific CSS — appended to _BASE_CSS via page_base."""
_REPORT_CSS = """\
.age { color: var(--muted); font-size: 0.75rem; display: block; margin-top: 2px; }
.badge.age-badge { margin-left: 8px; }
.fgi-components { margin-top: 10px; border-top: 1px solid var(--border);
        padding-top: 8px; display: grid; gap: 4px; font-size: 0.8rem; }
.fgi-components .comp { display: flex; justify-content: space-between;
        align-items: center; gap: 8px; }
.fgi-components .comp-name { color: var(--muted); }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 16px; }
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
.ticker { font-weight: 700; }
.name { color: var(--muted); font-size: 0.8rem; }
.ticker-meta { display: block; color: var(--muted); font-size: 0.72rem;
        line-height: 1.4; margin-top: 2px; }
.meta-tier { color: var(--accent); font-weight: 600; }
.meta-validity { color: var(--muted); }
.meta-role { color: var(--muted); font-style: italic; }
.meta-notes { color: var(--muted); opacity: 0.85; }
.legend { margin-top: 24px; }
.legend-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
        gap: 12px; }
.legend-card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 12px 16px; }
.legend-card summary { cursor: pointer; font-weight: 600; font-size: 0.9rem;
        display: flex; justify-content: space-between; align-items: center;
        gap: 8px; list-style: none; }
.legend-card summary::-webkit-details-marker { display: none; }
.legend-card summary::after { content: "\\2139\\fe0f"; font-size: 0.9rem; }
.legend-card[open] summary::after { content: "\\2716"; font-size: 0.9rem; }
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
/* Sort & filter tabelle ticker */
table.ticker-table th.sortable { cursor: pointer; user-select: none; }
table.ticker-table th.sorted { color: var(--neutral); }
.sort-ind { white-space: pre; }
.filter-icon { cursor: pointer; margin-left: 5px; display: inline-flex;
        color: var(--muted); opacity: 0.55; vertical-align: middle;
        border-radius: 4px; padding: 1px; }
.filter-icon:hover { opacity: 1; background: rgba(88, 166, 255, 0.15); }
.filter-icon.active { color: var(--neutral); opacity: 1;
        background: rgba(88, 166, 255, 0.2); }
.filter-popup { position: absolute; z-index: 1000; background: var(--card);
        border: 1px solid var(--border); border-radius: 10px; padding: 12px;
        box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35); display: flex;
        flex-direction: column; gap: 10px; min-width: 190px; }
.filter-popup .popup-title { font-size: 0.78rem; color: var(--muted);
        text-transform: uppercase; letter-spacing: 0.05em; }
.filter-popup input, .filter-popup select { background: var(--bg);
        color: var(--text); border: 1px solid var(--border);
        border-radius: 6px; padding: 6px 8px; font-size: 0.85rem; width: 100%;
        box-sizing: border-box; }
.num-filter { display: flex; gap: 6px; }
.num-filter select { width: auto; flex: 0 0 auto; }
.popup-actions { display: flex; gap: 8px; justify-content: flex-end; }
.popup-actions button { cursor: pointer; border: none; border-radius: 8px;
        padding: 6px 14px; font-size: 0.82rem; font-weight: 600; }
.popup-apply { background: var(--green); color: #fff; }
.popup-clear { background: var(--bg); color: var(--text);
        border: 1px solid var(--border) !important; }
.table-tools { display: flex; justify-content: flex-end; margin-bottom: 6px; }
.table-reset { background: var(--card); color: var(--text);
        border: 1px solid var(--border); border-radius: 8px;
        padding: 4px 10px; cursor: pointer; font-size: 0.8rem; }
.table-reset:hover { opacity: 0.85; }
.legend-strategy { margin-top: 8px; font-size: 0.85rem;
        background: rgba(88, 166, 255, 0.08);
        border-left: 3px solid var(--neutral); padding: 6px 10px;
        border-radius: 6px; }
.portfolio-summary .pnl-pos { color: var(--green); font-weight: 600; }
.portfolio-summary .pnl-neg { color: var(--red); font-weight: 600; }
"""

"""Report-specific script — age badges for data-fetched-at elements."""
_REPORT_SCRIPT = """\
<script>
(function () {
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
      : "aggiornato " + fmtAge(ageMs) + " \\u00b7 " + fmtRemaining(staleMs - ageMs);
    var badge = document.createElement("span");
    badge.className = "badge age-badge " + status;
    badge.textContent = status;
    var value = el.querySelector(".value");
    if (value) { value.parentNode.insertBefore(badge, value.nextSibling); }
    else { var fc = el.querySelector("td:first-child"); if (fc) fc.appendChild(badge); }
    var age = document.createElement("span");
    age.className = "age";
    age.textContent = text;
    var metas = el.querySelectorAll(".meta");
    var meta = metas.length ? metas[metas.length - 1] : null;
    if (meta) { meta.appendChild(age); }
    else { var lc = el.querySelector("td:last-child"); if (lc) lc.appendChild(age); }
  }
})();
</script>
"""


_TABLE_SCRIPT = """\
<script>
// --- Sort & filter per le tabelle ticker -------------------------------
// Sort ciclico per colonna: click → asc, click → desc, click → nessuno
// (un solo ordinamento alla volta). Filtri in POPUP: icona imbuto sulla
// testata apre il pannello; applicare/pulire lo chiude. L'icona cambia
// colore quando la colonna ha un filtro attivo. Nessun input nelle
// intestazioni → le colonne non si allargano.
(function () {
  var NUM_OPS = [">", "≥", "=", "≤", "<"];
  var DATE_OPTS = [
    ["today", "oggi"],
    ["yesterday", "ieri"],
    ["7d", "ultimi 7 giorni"],
    ["older", "più vecchio di 7 giorni"]
  ];
  var FUNNEL =
    '<svg viewBox="0 0 16 16" width="11" height="11" aria-hidden="true">' +
    '<path d="M1.5 2h13L9.5 8.2v4.6l-3 1.7V8.2z" fill="currentColor"/></svg>';

  // Popup unico condiviso tra tutte le tabelle
  var popup = null;
  function ensurePopup() {
    if (!popup) {
      popup = document.createElement("div");
      popup.className = "filter-popup";
      popup.style.display = "none";
      document.body.appendChild(popup);
      document.addEventListener("mousedown", function (ev) {
        if (popup.style.display === "none") return;
        if (!popup.contains(ev.target)) hidePopup();
      });
      document.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape") hidePopup();
      });
    }
    return popup;
  }
  function hidePopup() { if (popup) popup.style.display = "none"; }

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

  function setupTable(table) {
    var thead = table.tHead;
    var headCells = thead.rows[0].cells;
    var tbody = table.tBodies[0];
    var dataRows = Array.prototype.slice.call(tbody.rows);
    var sortCol = -1, sortDir = 0;          // 0 = nessun ordinamento
    var filterStates = [];                  // per colonna: null | stato
    dataRows.forEach(function (r, i) { r.setAttribute("data-orig-index", i); });

    // Toolbar con reset totale (filtri + ordinamento)
    var tools = document.createElement("div");
    tools.className = "table-tools";
    var resetBtn = document.createElement("button");
    resetBtn.type = "button";
    resetBtn.className = "table-reset";
    resetBtn.textContent = "↺ Azzera filtri e ordine";
    tools.appendChild(resetBtn);
    table.parentNode.insertBefore(tools, table);

    function passes(row) {
      for (var idx = 0; idx < headCells.length; idx++) {
        var f = filterStates[idx];
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

    function apply() {
      var visible = [];
      dataRows.forEach(function (row) {
        var ok = passes(row);
        row.style.display = ok ? "" : "none";
        if (ok) visible.push(row);
      });
      if (sortCol >= 0 && sortDir !== 0) {
        var type = headCells[sortCol].getAttribute("data-type") || "text";
        visible.sort(function (a, b) {
          var va = cellValue(a, sortCol, type), vb = cellValue(b, sortCol, type);
          if (va === null && vb === null) return 0;
          if (va === null) return 1;        // valori mancanti sempre in fondo
          if (vb === null) return -1;
          var cmp = (type === "text")
            ? va.localeCompare(vb)
            : (va < vb ? -1 : va > vb ? 1 : 0);
          return cmp * sortDir;
        });
      } else {
        visible.sort(function (a, b) {
          return (+a.getAttribute("data-orig-index")) -
                 (+b.getAttribute("data-orig-index"));
        });
      }
      visible.forEach(function (row) { tbody.appendChild(row); });
    }

    function updateIndicators() {
      Array.prototype.forEach.call(headCells, function (th, idx) {
        var ind = th.querySelector(".sort-ind");
        if (ind) ind.textContent =
          idx === sortCol && sortDir !== 0 ? (sortDir === 1 ? " ▲" : " ▼") : "";
        th.classList.toggle("sorted", idx === sortCol && sortDir !== 0);
      });
    }

    function updateIcons() {
      Array.prototype.forEach.call(headCells, function (th, idx) {
        var icon = th.querySelector(".filter-icon");
        if (icon) icon.classList.toggle("active", !!filterStates[idx]);
      });
    }

    function openFilterPopup(idx, type, icon) {
      var p = ensurePopup();
      p.innerHTML = "";
      var st = filterStates[idx];

      var title = document.createElement("div");
      title.className = "popup-title";
      title.textContent = "Filtra: " +
        headCells[idx].textContent.replace(/[▲▼]/g, "").trim();
      p.appendChild(title);

      var readControl;   // legge i controlli → aggiorna filterStates[idx]
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
        if (st) { sel.value = st.op; inp.value = String(st.num).replace(".", ","); }
        wrap.appendChild(sel); wrap.appendChild(inp);
        p.appendChild(wrap);
        readControl = function () {
          var v = inp.value.trim().replace(",", ".");
          filterStates[idx] = v ? { op: sel.value, num: parseFloat(v) } : null;
        };
        inp.addEventListener("keydown", function (ev) {
          if (ev.key === "Enter") { readControl(); closeAndApply(); }
        });
        setTimeout(function () { inp.focus(); }, 0);
      } else if (type === "date") {
        var selD = document.createElement("select");
        var none = document.createElement("option");
        none.value = ""; none.textContent = "(qualsiasi data)";
        selD.appendChild(none);
        DATE_OPTS.forEach(function (pair) {
          var o = document.createElement("option");
          o.value = pair[0]; o.textContent = pair[1]; selD.appendChild(o);
        });
        if (st) selD.value = st;
        p.appendChild(selD);
        readControl = function () { filterStates[idx] = selD.value || null; };
        selD.addEventListener("change", function () { readControl(); closeAndApply(); });
      } else {
        var inpT = document.createElement("input");
        inpT.type = "text"; inpT.placeholder = "contiene…";
        if (st) inpT.value = st;
        p.appendChild(inpT);
        readControl = function () {
          filterStates[idx] = inpT.value.trim().toLowerCase() || null;
        };
        inpT.addEventListener("keydown", function (ev) {
          if (ev.key === "Enter") { readControl(); closeAndApply(); }
        });
        setTimeout(function () { inpT.focus(); }, 0);
      }

      var actions = document.createElement("div");
      actions.className = "popup-actions";
      var clearBtn = document.createElement("button");
      clearBtn.type = "button"; clearBtn.className = "popup-clear";
      clearBtn.textContent = "Pulisci";
      var applyBtn = document.createElement("button");
      applyBtn.type = "button"; applyBtn.className = "popup-apply";
      applyBtn.textContent = "Applica";
      actions.appendChild(clearBtn); actions.appendChild(applyBtn);
      p.appendChild(actions);

      function closeAndApply() { hidePopup(); updateIcons(); apply(); }
      applyBtn.addEventListener("click", function () {
        readControl(); closeAndApply();
      });
      clearBtn.addEventListener("click", function () {
        filterStates[idx] = null; closeAndApply();
      });

      // Posizionamento sotto l'icona (clamp ai bordi della finestra)
      p.style.display = "block";
      var r = icon.getBoundingClientRect();
      var left = r.left + window.scrollX - 70;
      left = Math.max(window.scrollX + 8,
        Math.min(left, window.scrollX + document.documentElement.clientWidth - p.offsetWidth - 12));
      p.style.top = (r.bottom + window.scrollY + 6) + "px";
      p.style.left = left + "px";
    }

    Array.prototype.forEach.call(headCells, function (th, idx) {
      var type = th.getAttribute("data-type") || "text";
      filterStates[idx] = null;

      // Icona filtro (il click NON deve innescare l'ordinamento)
      var icon = document.createElement("span");
      icon.className = "filter-icon";
      icon.innerHTML = FUNNEL;
      icon.title = "Filtra colonna";
      icon.addEventListener("click", function (ev) {
        ev.stopPropagation();
        openFilterPopup(idx, type, icon);
      });

      // Ordinamento ciclico sul th: asc → desc → nessuno
      th.classList.add("sortable");
      th.title = "Clicca: ordina ↑ / ↓ / ripristina";
      var ind = document.createElement("span");
      ind.className = "sort-ind";
      th.appendChild(ind);
      th.appendChild(icon);
      th.addEventListener("click", function (ev) {
        if (ev.target.closest && ev.target.closest(".filter-icon")) return;
        if (sortCol !== idx) { sortCol = idx; sortDir = 1; }
        else if (sortDir === 1) { sortDir = -1; }
        else { sortCol = -1; sortDir = 0; }
        updateIndicators();
        apply();
      });
    });

    resetBtn.addEventListener("click", function () {
      sortCol = -1; sortDir = 0;
      filterStates = headCells.length ? new Array(headCells.length).fill(null) : [];
      updateIndicators();
      updateIcons();
      apply();
    });
  }

  document.querySelectorAll("table.ticker-table").forEach(setupTable);
})();
</script>
"""


def _report_pos_dict(pos) -> dict[str, Any]:
    """Convert a Position dataclass to a minimal dict for the report."""
    return {
        "ticker": pos.ticker,
        "quantity": pos.quantity,
        "avg_price": pos.average_entry_price,
        "last_price": pos.market_price,
        "unrealized_pnl_pct": pos.unrealized_pnl_pct,
    }


def render_portfolio_summary(data: dict[str, Any]) -> str:
    """Render a lightweight portfolio summary section for the main report.

    Shows a compact table with open positions and SELL signals.
    Links to the full portfolio page for details.
    """
    try:
        import sqlite3
        from portfolio import calculate_positions
        from portfolio_db import get_transactions, init_db
        from sell_strategy import evaluate_all, load_rules
    except ImportError:
        return ""

    project_root = Path(__file__).resolve().parent.parent
    db_path = str(project_root / "output" / "portfolio.db")
    try:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_db(conn)
        txs = get_transactions(conn)
        conn.close()
    except Exception:
        return ""
    if not txs:
        return ""

    # Build prices from output.json ohlcv section
    prices: dict[str, float] = {}
    ohlcv = data.get("ohlcv", {})
    for category in ohlcv.values():
        if not isinstance(category, dict):
            continue
        for ticker, entry in category.items():
            if isinstance(entry, dict) and "last_close" in entry:
                try:
                    prices[ticker] = float(entry["last_close"])
                except (TypeError, ValueError):
                    pass

    result = calculate_positions(txs, prices=prices)
    positions = [_report_pos_dict(pos) for pos in result.positions.values()]
    if not positions:
        return ""

    rules = load_rules()
    evaluations = evaluate_all(
        [{"ticker": p["ticker"], "quantity": p["quantity"],
          "unrealized_pnl_pct": p["unrealized_pnl_pct"]}
         for p in positions],
        data,
        rules=rules,
    )
    eval_map = {ev.ticker: ev for ev in evaluations}

    rows = ""
    for p in positions:
        ev = eval_map.get(p["ticker"])
        signal = ev.sell_signal if ev else "—"
        signal_class = signal.split(" ")[0] if ev else ""
        gain_pct = p.get("unrealized_pnl_pct")
        gain_cls = "pnl-pos" if (gain_pct or 0) > 0 else "pnl-neg" if (gain_pct or 0) < 0 else ""
        gain_str = f"{gain_pct:.1f}%" if gain_pct is not None else "—"
        last_price_str = f"${p['last_price']:.2f}" if p.get('last_price') else "—"
        rows += (
            f"<tr><td><strong>{html_mod.escape(p['ticker'])}</strong></td>"
            f"<td>{p['quantity']}</td>"
            f"<td>${p['avg_price']:.2f}</td>"
            f"<td>{last_price_str}</td>"
            f'<td class="{gain_cls}">{gain_str}</td>'
            f'<td><span class="sell-signal sell-{signal_class}">{html_mod.escape(signal)}</span></td>'
            "</tr>"
        )

    return _collapsible(
        "💼 Portafoglio",
        '<div class="portfolio-summary">'
        f'<p style="font-size:0.85rem;color:var(--muted);">'
        f'{len(positions)} posizioni aperte — '
        '<a href="/portfolio.html" style="color:var(--green);">dettagli completa →</a></p>'
        '<table class="ticker-table"><thead><tr>'
        "<th>Ticker</th><th>Qtà</th><th>Prezzo medio</th>"
        "<th>Ultimo prezzo</th><th>Gain/Loss %</th><th>Segnale SELL</th>"
        "</tr></thead><tbody>"
        f"{rows}"
        "</tbody></table></div>"
    )


def build_page(data: dict[str, Any], tickers_config: dict[str, Any] | None = None) -> str:
    """Assemble the complete HTML document.

    ``tickers_config`` (optional) is the normalized ``tickers`` section from
    config.yaml; used only for display metadata and tier ordering.
    """
    stale = data.get("stale_summary", {})
    overall = "fresh" if stale.get("stale", 0) == 0 else "stale"
    title = "Market Dashboard"

    header = render_header(
        "report", f"📊 {title}",
        f"Generato: {format_iso_dt(data.get('generated_at'))}",
        extra_badge=f'<span class="badge {overall}">{overall}</span>',
    )
    content = (
        '<div class="sections-toolbar">'
        '<button id="sections-toggle" type="button">\U0001f5c2\ufe0f Chiudi tutte</button>'
        "</div>"
        f"{_collapsible('Indicatori di mercato', render_market_cards(data))}"
        f"{_ticker_sections(data, tickers_config)}"
        f"{render_portfolio_summary(data)}"
        f"{render_indicator_matrix(data.get('strategy_indicators', {}))}"
        f"{render_stale_summary(stale)}"
        f"{render_legend()}"
    )
    return wrap_page(
        title, "report", _REPORT_CSS, header, content,
        scripts=f"{_REPORT_SCRIPT}{_TABLE_SCRIPT}",
    )


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
