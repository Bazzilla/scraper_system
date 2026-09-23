"""Shared page building blocks — CSS, HTML wrapper, JS helpers.

All page generators import from here instead of duplicating boilerplate.
"""

from __future__ import annotations

import html as html_mod
from typing import Any

from report_helpers import FAVICON_LINK, render_nav

# ── Version ─────────────────────────────────────────────────────────────────
VERSION_MAJOR = 0
VERSION_MINOR = 5
VERSION_BUILD = 1
VERSION = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_BUILD}"

# ── Base CSS (shared by all pages) ──────────────────────────────────────────

_BASE_CSS = """\
:root { --bg: #0f1419; --card: #1a212b; --border: #2c3542; --text: #e6edf3;
        --muted: #8b949e; --green: #2ea043; --yellow: #d29922; --red: #f85149;
        --neutral: #58a6ff; --container-max: 1100px; }
[data-theme="light"] { --bg: #f6f8fa; --card: #ffffff; --border: #d0d7de;
        --text: #1f2328; --muted: #57606a; --green: #1a7f37; --yellow: #9a6700;
        --red: #cf222e; --neutral: #0969da; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        sans-serif; background: var(--bg); color: var(--text); line-height: 1.5;
        padding: 24px; }
.container { max-width: var(--container-max); margin: 0 auto; }
header { display: flex; flex-direction: column; align-items: flex-start;
        gap: 8px; margin-bottom: 24px; }
h1 { font-size: 1.5rem; }
h2 { margin: 28px 0 12px; font-size: 1.15rem; }
.sub { color: var(--muted); font-size: 0.9rem; }
.badge { padding: 2px 10px; border-radius: 999px; font-size: 0.8rem;
        font-weight: 600; }
.badge.fresh { background: var(--green); color: #fff; }
.badge.stale { background: var(--red); color: #fff; }
button#theme-toggle { background: var(--card); color: var(--text);
        border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px;
        cursor: pointer; font-size: 0.9rem; }
.page-nav { display: inline-flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.page-nav a { padding: 4px 12px; border-radius: 999px; font-size: 0.85rem;
        font-weight: 600; text-decoration: none; background: var(--card);
        color: var(--text); border: 1px solid var(--border); }
.page-nav a.active { background: var(--green); color: #fff;
        border-color: var(--green); }
.page-nav a:hover { opacity: 0.85; }
button#sections-toggle { background: var(--card); color: var(--text);
        border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px;
        cursor: pointer; font-size: 0.9rem; }
.sections-toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
/* Shared card */
.card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 16px; }
/* Shared table */
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
/* Shared message feedback */
.msg { padding: 8px 12px; border-radius: 8px; font-size: 0.9rem; }
.msg.ok { background: var(--green); color: #fff; }
.msg.err { background: var(--red); color: #fff; }
/* Shared buttons */
button { cursor: pointer; border: none; border-radius: 8px; padding: 6px 12px;
        font-size: 0.85rem; font-weight: 600; }
button.primary { background: var(--green); color: #fff; }
button.danger { background: var(--red); color: #fff; }
button.subtle { background: var(--bg); color: var(--text);
        border: 1px solid var(--border); }
/* Shared collapsible details */
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
/* Shared footer */
footer { margin-top: 32px; color: var(--muted); font-size: 0.85rem;
        border-top: 1px solid var(--border); padding-top: 16px; }
/* System title */
.system-title { font-size: 0.75rem; color: var(--muted); margin-bottom: 4px;
        letter-spacing: 0.05em; text-transform: uppercase; }
.system-version { font-weight: 400; margin-left: 6px; opacity: 0.7; }
/* Ticker link style — shared across all pages (report, portfolio, etc.) */
.ticker { font-weight: 700; }
.ticker a { color: inherit; text-decoration: none; }
.ticker a:hover { color: var(--neutral); text-decoration: underline; }
/* Ticker meta icons (note / price of interest) + edit affordance */
.ti-icon { background: none; border: none; padding: 0 1px; font-size: 0.85em;
        cursor: pointer; vertical-align: middle; line-height: 1; }
.ti-edit { opacity: 0.4; }
.ti-edit:hover { opacity: 1; }
/* Ticker meta modal (shared) */
.tm-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.55);
        display: flex; align-items: center; justify-content: center;
        z-index: 1000; padding: 16px; }
.tm-overlay[hidden] { display: none; }
.tm-dialog { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 20px; width: min(440px, 100%);
        max-height: 90vh; overflow-y: auto; }
.tm-dialog h3 { margin: 0 0 4px; font-size: 1.05rem; }
.tm-meta { color: var(--muted); font-size: 0.85rem; margin-bottom: 12px; }
.tm-meta strong { color: var(--text); }
.tm-field { display: flex; flex-direction: column; gap: 4px;
        margin-bottom: 12px; font-size: 0.85rem; color: var(--muted); }
.tm-field input, .tm-field textarea { background: var(--bg); color: var(--text);
        border: 1px solid var(--border); border-radius: 6px; padding: 8px;
        font-size: 0.9rem; font-family: inherit; }
.tm-field textarea { resize: vertical; min-height: 72px; }
.tm-hint { font-size: 0.75rem; color: var(--muted); text-align: right; }
.tm-actions { display: flex; gap: 8px; justify-content: flex-end;
        flex-wrap: wrap; margin-top: 4px; }
.tm-msg { margin-top: 10px; font-size: 0.85rem; min-height: 1.2em; }
.tm-msg.ok { color: var(--green); }
.tm-msg.err { color: var(--red); }
/* Shared sell signal badges */
.sell-signal { display: inline-block; padding: 2px 8px; border-radius: 6px;
        font-size: 0.75rem; font-weight: 600; }
.sell-NESSUNA { background: var(--card); color: var(--muted); }
.sell-MANTIENI { background: #1a3a1a; color: #4ade80; }
.sell-PRENDI { background: #3a2a0a; color: #fbbf24; }
.sell-RIDUCI { background: #3a1a1a; color: #f87171; }
.sell-ATTENZIONE { background: #2a1a3a; color: #c084fc; }
/* Shared P/L classes */
.pnl-pos { color: var(--green); font-weight: 600; }
.pnl-neg { color: var(--red); font-weight: 600; }
"""

# ── Shared JS (theme toggle + helpers) ──────────────────────────────────────

_SHARED_SCRIPT = """\
<script>
(function () {
  /* Theme toggle */
  var saved = localStorage.getItem("report-theme");
  var theme = saved || "dark";
  document.documentElement.setAttribute("data-theme", theme);
  var btn = document.getElementById("theme-toggle");
  if (btn) {
    btn.textContent = theme === "dark" ? "\\u2600\\ufe0f Light" : "\\ud83c\\udf19 Dark";
    btn.addEventListener("click", function () {
      var next = theme === "dark" ? "light" : "dark";
      theme = next;
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("report-theme", next);
      btn.textContent = next === "dark" ? "\\u2600\\ufe0f Light" : "\\ud83c\\udf19 Dark";
    });
  }

  /* Collapsible sections toggle */
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
      sectionsBtn.textContent = allOpen() ? "\\ud83d\\uddc2\\ufe0f Chiudi tutte" : "\\ud83d\\uddc2\\ufe0f Apri tutte";
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

  /* Shared helpers — available to page scripts */
  window.__helpers = {
    $: function (id) { return document.getElementById(id); },
    fmt: function (v) {
      if (v == null) return "\\u2014";
      return v.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    },
    fmtDate: function (iso) {
      if (!iso) return "\\u2014";
      var p = iso.split("-");
      return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : iso;
    },
    pnlClass: function (v) {
      if (v == null) return "neutral";
      return v >= 0 ? "pnl-pos" : "pnl-neg";
    },
    valClass: function (v) {
      if (v == null) return "neutral";
      return v >= 0 ? "positive" : "negative";
    },
    postJSON: function (url, payload, attempt) {
      return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).then(function (resp) {
        if (resp.status === 401 && (attempt || 0) < 2) {
          return window.__helpers.postJSON(url, payload, (attempt || 0) + 1);
        }
        return resp.json();
      });
    },
    api: function (method, path, body) {
      var opts = {method: method, headers: {"Content-Type": "application/json"}};
      if (body) opts.body = JSON.stringify(body);
      return fetch(path, opts).then(function (r) {
        return r.json().then(function (d) { return {status: r.status, data: d}; });
      });
    }
  };

  /* ── Ticker meta modal (note + price of interest) ─────────────────── */
  function ensureTickerModal() {
    if (document.getElementById("ticker-modal")) return;
    var wrap = document.createElement("div");
    wrap.id = "ticker-modal";
    wrap.className = "tm-overlay";
    wrap.hidden = true;
    wrap.innerHTML =
      '<div class="tm-dialog" role="dialog" aria-modal="true" ' +
      'aria-labelledby="tm-title">' +
      '<h3 id="tm-title"></h3>' +
      '<div class="tm-meta" id="tm-meta"></div>' +
      '<label class="tm-field">Prezzo di interesse (USD)' +
      '<input id="tm-poi" type="number" step="0.01" min="0" ' +
      'placeholder="es. 178.50"></label>' +
      '<label class="tm-field">Nota' +
      '<textarea id="tm-note" maxlength="1000" rows="4" ' +
      'placeholder="Accumulo sotto 180, ETF flows ok…"></textarea>' +
      '<span class="tm-hint"><span id="tm-count">0</span>/1000</span></label>' +
      '<div class="tm-actions">' +
      '<button type="button" class="subtle" id="tm-clear">Svuota nota</button>' +
      '<button type="button" class="subtle" id="tm-cancel">Annulla</button>' +
      '<button type="button" class="primary" id="tm-save">Salva</button>' +
      '</div><div class="tm-msg" id="tm-msg" role="status"></div></div>';
    document.body.appendChild(wrap);

    var note = document.getElementById("tm-note");
    var count = document.getElementById("tm-count");
    note.addEventListener("input", function () { count.textContent = note.value.length; });

    function close() { wrap.hidden = true; }
    document.getElementById("tm-cancel").addEventListener("click", close);
    wrap.addEventListener("click", function (e) { if (e.target === wrap) close(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !wrap.hidden) close();
    });
    document.getElementById("tm-clear").addEventListener("click", function () {
      note.value = "";
      count.textContent = "0";
    });
    document.getElementById("tm-save").addEventListener("click", function () {
      var symbol = wrap.dataset.symbol;
      var poiRaw = document.getElementById("tm-poi").value.trim();
      var payload = {
        symbol: symbol,
        notes: note.value,
        price_of_interest: poiRaw === "" ? null : Number(poiRaw)
      };
      var msg = document.getElementById("tm-msg");
      msg.className = "tm-msg";
      msg.textContent = "Salvataggio…";
      window.__helpers.api("POST", "/api/ticker-meta", payload).then(function (r) {
        if (r.data && r.data.ok) {
          msg.className = "tm-msg ok";
          msg.textContent = "Salvato — report rigenerato…";
          setTimeout(function () { location.reload(); }, 600);
        } else {
          msg.className = "tm-msg err";
          msg.textContent = (r.data && r.data.message) || "Errore nel salvataggio";
        }
      }).catch(function () {
        msg.className = "tm-msg err";
        msg.textContent = "Errore di connessione";
      });
    });
  }

  function openTickerModal(symbol) {
    ensureTickerModal();
    var wrap = document.getElementById("ticker-modal");
    wrap.dataset.symbol = symbol;
    document.getElementById("tm-title").textContent = symbol;
    document.getElementById("tm-meta").innerHTML = "Caricamento…";
    document.getElementById("tm-poi").value = "";
    document.getElementById("tm-note").value = "";
    document.getElementById("tm-count").textContent = "0";
    var msg = document.getElementById("tm-msg");
    msg.className = "tm-msg";
    msg.textContent = "";
    wrap.hidden = false;
    window.__helpers.api("GET", "/api/ticker-meta?symbol=" +
      encodeURIComponent(symbol)).then(function (r) {
      var d = (r.data && r.data.ok) ? r.data : null;
      if (!d) {
        document.getElementById("tm-meta").innerHTML =
          ((r.data && r.data.message) || "Ticker non trovato in config.yaml");
        return;
      }
      document.getElementById("tm-meta").innerHTML =
        "<strong>" + (d.name || d.symbol) + "</strong>" +
        (d.last_close != null
          ? " · prezzo attuale <strong>$" +
            Number(d.last_close).toFixed(2) + "</strong>"
          : " · prezzo attuale —");
      if (d.price_of_interest != null) {
        document.getElementById("tm-poi").value = d.price_of_interest;
      }
      if (d.notes) {
        document.getElementById("tm-note").value = d.notes;
        document.getElementById("tm-count").textContent = String(d.notes.length);
      }
    }).catch(function () {
      document.getElementById("tm-meta").textContent = "Errore di connessione";
    });
  }
  window.openTickerModal = openTickerModal;

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-ticker-edit]");
    if (btn) {
      e.preventDefault();
      openTickerModal(btn.getAttribute("data-ticker-edit"));
    }
  });
})();
</script>"""


# ── HTML wrapper ────────────────────────────────────────────────────────────

def wrap_page(
    title: str,
    nav_active: str,
    css: str,
    header_html: str,
    content_html: str,
    scripts: str = "",
    *,
    extra_head: str = "",
) -> str:
    """Build a complete HTML page following the standard pattern:
    nav → title → content → footer (optional).

    Args:
        title: Page title (also used in <title>).
        nav_active: Active nav item key (e.g. "report", "portfolio").
        css: Page-specific CSS (appended to _BASE_CSS).
        header_html: Inner HTML of <header> (nav + title already wrapped).
        content_html: Inner HTML of <main> or direct content after header.
        scripts: Page-specific <script> tags (appended after _SHARED_SCRIPT).
        extra_head: Extra content inside <head> (e.g. JSON data script).
    """
    return (
        "<!DOCTYPE html>\n<html lang=\"it\" data-theme=\"dark\">\n<head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"{FAVICON_LINK}"
        f"<title>SC - {title}</title>"
        f"{extra_head}"
        f"<style>{_BASE_CSS}{css}</style>"
        "</head>\n<body><div class=\"container\">"
        f"{header_html}"
        f"{content_html}"
        "</div>"
        f"{_SHARED_SCRIPT}"
        f"{scripts}"
        "</body>\n</html>"
    )


def render_ticker(symbol: str, meta: dict[str, Any] | None = None) -> str:
    """Render a ticker cell: Yahoo link + note/price icons + edit button.

    The edit button (and the presence icons) open the shared ticker-meta
    modal (see _SHARED_SCRIPT) via the ``data-ticker-edit`` attribute.

    Args:
        symbol: Ticker symbol (e.g. "NVDA").
        meta: Optional ticker metadata from config.yaml (``notes``,
            ``price_of_interest``). None → only the edit button is shown.
    """
    esc = html_mod.escape
    s = esc(symbol)
    meta = meta or {}
    icons = ""
    note = meta.get("notes")
    if note:
        icons += (
            f'<button type="button" class="ti-icon ti-note" '
            f'data-ticker-edit="{s}" title="{esc(str(note))}" '
            f'aria-label="Nota presente">📝</button>'
        )
    poi = meta.get("price_of_interest")
    if poi is not None:
        icons += (
            f'<button type="button" class="ti-icon ti-price" '
            f'data-ticker-edit="{s}" '
            f'title="Prezzo di interesse: ${esc(str(poi))}" '
            f'aria-label="Prezzo di interesse presente">🎯</button>'
        )
    icons += (
        f'<button type="button" class="ti-icon ti-edit" '
        f'data-ticker-edit="{s}" title="Modifica nota/prezzo" '
        f'aria-label="Modifica nota e prezzo di interesse">✏️</button>'
    )
    return (
        f'<span class="ticker">'
        f'<a href="https://finance.yahoo.com/quote/{s}/" '
        f'target="_blank" rel="noopener">{s}</a>{icons}</span>'
    )


def render_header(
    nav_active: str,
    title: str,
    subtitle: str = "",
    *,
    extra_badge: str = "",
) -> str:
    """Render the standard page header: nav bar first, then title.

    Args:
        nav_active: Active nav item key.
        title: Page title (h1).
        subtitle: Optional subtitle text.
        extra_badge: Optional HTML to insert before nav (e.g. fresh/stale badge).
    """
    badge_html = f'{extra_badge} ' if extra_badge else ""
    sub_html = f'<div class="sub">{subtitle}</div>' if subtitle else ""
    return (
        "<header>"
        '<div class="system-title">SCRAPER-SYSTEM '
        f'<span class="system-version">v{VERSION}</span></div>'
        f"<div>{badge_html}{render_nav(nav_active)} "
        '<button id="theme-toggle" type="button">☀️ Light</button></div>'
        f"<div><h1>{title}</h1>"
        f"{sub_html}</div>"
        "</header>"
    )
