"""Scraper-run page generator.

Builds a static HTML page (same styles as the dashboard) that lets the user
launch the general scraping pipeline (``run.py``) from the browser with
selectable flags.  Output is streamed via Server-Sent Events (SSE) so the
user sees the log in real time.

The page is server-rendered by ``GET /scraper-run.html`` from the overrides
server; the JS opens an ``EventSource`` to ``GET /api/scraper-run?mode=...``
which runs ``run.py`` in a subprocess and streams stdout line-by-line.
"""

from __future__ import annotations

from report_html import _CSS, _SCRIPT
from report_helpers import FAVICON_LINK, render_nav

_PAGE_CSS = _CSS + """\
.run-card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 16px; margin-top: 20px; }
.mode-select { display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }
.mode-select label { color: var(--text); font-size: 0.9rem; cursor: pointer;
        display: flex; align-items: flex-start; gap: 8px; }
.mode-select .desc { color: var(--muted); font-size: 0.85rem; margin-left: 24px; }
.run-btn { background: var(--green); color: #fff; border: none; border-radius: 8px;
        padding: 10px 20px; cursor: pointer; font-size: 1rem; font-weight: 600; }
.run-btn:hover { opacity: 0.9; }
.run-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.output-card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; margin-top: 20px; overflow: hidden; }
.output-header { padding: 10px 16px; border-bottom: 1px solid var(--border);
        font-weight: 600; font-size: 0.9rem; }
#output { margin: 0; padding: 16px; font-family: monospace; font-size: 0.85rem;
        max-height: 500px; overflow-y: auto; white-space: pre-wrap;
        word-break: break-word; background: var(--bg); min-height: 200px; }
"""

_MODE_OPTIONS = """\
<div class="mode-select">
  <label>
    <input type="radio" name="mode" value="full" checked>
    <span><strong>Pipeline completa</strong><br>
    <span class="desc">Esegue lo scraping di tutti gli indicatori, consolida
    i dati e genera il report HTML. Circa 2 minuti.</span></span>
  </label>
  <label>
    <input type="radio" name="mode" value="report_only">
    <span><strong>Solo report</strong><br>
    <span class="desc">Ri-genera il report HTML dai dati già salvati in
    output.json. Nessuno scraping, istantaneo.</span></span>
  </label>
  <label>
    <input type="radio" name="mode" value="override_only">
    <span><strong>Solo override</strong><br>
    <span class="desc">Applica gli override manuali a output.json e rigenera
    il report. Utile dopo aver modificato i valori manuali.</span></span>
  </label>
</div>
<button id="run-btn" class="run-btn" type="button">▶ Avvia</button>
"""

_RUN_SCRIPT = """\
(function () {
  var btn = document.getElementById("run-btn");
  var output = document.getElementById("output");

  btn.addEventListener("click", function () {
    var mode = document.querySelector('input[name="mode"]:checked').value;
    btn.disabled = true;
    btn.textContent = "⏳ In corso...";
    output.textContent = "";

    var evtSource = new EventSource("/api/scraper-run?mode=" + encodeURIComponent(mode));
    evtSource.onmessage = function (e) {
      output.textContent += e.data + "\\n";
      output.scrollTop = output.scrollHeight;
    };
    evtSource.addEventListener("done", function (e) {
      evtSource.close();
      btn.disabled = false;
      btn.textContent = "▶ Avvia";
      var code = parseInt(e.data, 10);
      output.textContent += "\\n" + (code === 0
        ? "✅ Completato" : "❌ Fallito (exit " + code + ")");
      output.scrollTop = output.scrollHeight;
    });
    evtSource.onerror = function () {
      evtSource.close();
      btn.disabled = false;
      btn.textContent = "▶ Avvia";
      output.textContent += "\\n❌ Errore di connessione";
    };
  });
})();
"""


def render_scraper_run_page() -> str:
    """Render the scraper-run launch page."""
    return (
        "<!DOCTYPE html>\n<html lang=\"it\" data-theme=\"dark\">\n<head>"
        "<meta charset=\"utf-8\">"
        f"{FAVICON_LINK}"
        "<title>Esecuzione scraping</title>"
        f"<style>{_PAGE_CSS}</style>"
        "</head>\n<body><div class=\"container\">"
        "<header>"
        "<div><h1>🚀 Esecuzione scraping</h1>"
        '<div class="sub">Lancia la pipeline di scraping dal browser</div></div>'
        f'<div>{render_nav("scraper-run")} '
        '<button id="theme-toggle" type="button">☀️ Light</button></div>'
        "</header>"
        f'<div class="run-card">{_MODE_OPTIONS}</div>'
        '<div class="output-card">'
        '<div class="output-header">Output</div>'
        '<pre id="output"></pre>'
        "</div>"
        "</div>"
        f"{_SCRIPT}"
        f"<script>{_RUN_SCRIPT}</script>"
        "</body>\n</html>"
    )
