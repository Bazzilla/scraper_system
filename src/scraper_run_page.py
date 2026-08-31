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

from page_base import _SHARED_SCRIPT, render_header, wrap_page

_SCRAPER_RUN_CSS = """\
.run-card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 16px; margin-top: 20px; }
.mode-select { display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }
.mode-select label { color: var(--text); font-size: 0.9rem; cursor: pointer;
        display: flex; align-items: flex-start; gap: 8px; }
.mode-select .desc { color: var(--muted); font-size: 0.85rem; margin-left: 24px; }
.mode-extra { margin-left: 24px; margin-top: -4px; margin-bottom: 4px;
        display: none; }
.mode-extra.visible { display: block; }
.cat-select { background: var(--bg); color: var(--text);
        border: 1px solid var(--border); border-radius: 6px;
        padding: 6px 8px; font-size: 0.9rem; width: 280px; }
.cat-count { color: var(--muted); font-size: 0.85rem; margin-left: 8px; }
.ticker-search { position: relative; }
.ticker-input { background: var(--bg); color: var(--text);
        border: 1px solid var(--border); border-radius: 6px;
        padding: 6px 8px; font-size: 0.9rem; width: 280px; }
.ticker-results { position: absolute; top: 100%; left: 0; right: 0;
        background: var(--card); border: 1px solid var(--border);
        border-radius: 6px; max-height: 200px; overflow-y: auto;
        z-index: 10; display: none; }
.ticker-results.open { display: block; }
.ticker-result-item { padding: 6px 8px; cursor: pointer; font-size: 0.85rem; }
.ticker-result-item:hover { background: var(--bg); }
.ticker-result-item .sym { font-weight: 700; }
.ticker-result-item .cat { color: var(--muted); font-size: 0.8rem; }
.run-btn { background: var(--green); color: #fff; border: none; border-radius: 8px;
        padding: 10px 20px; cursor: pointer; font-size: 1rem; font-weight: 600; }
.run-btn:hover { opacity: 0.9; }
.run-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.status-bar { padding: 8px 16px; border-radius: 8px; margin-top: 12px;
        font-size: 0.9rem; font-weight: 600; display: none; }
.status-bar.running { display: block; background: var(--yellow); color: #000; }
.status-bar.done { display: block; background: var(--green); color: #fff; }
.status-bar.error { display: block; background: var(--red); color: #fff; }
.output-card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; margin-top: 20px; overflow: hidden; }
.output-header { padding: 10px 16px; border-bottom: 1px solid var(--border);
        font-weight: 600; font-size: 0.9rem; display: flex;
        align-items: center; justify-content: space-between; }
.clear-btn { background: none; border: 1px solid var(--border); color: var(--muted);
        border-radius: 6px; padding: 2px 8px; font-size: 0.8rem; cursor: pointer; }
.clear-btn:hover { color: var(--text); border-color: var(--text); }
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
  <label>
    <input type="radio" name="mode" value="category">
    <span><strong>Singola categoria</strong><br>
    <span class="desc">Scraping dei soli ticker di una categoria.</span></span>
  </label>
  <div id="cat-extra" class="mode-extra">
    <select id="category-select" class="cat-select" disabled>
      <option value="">Seleziona categoria...</option>
    </select>
    <span id="cat-count" class="cat-count"></span>
  </div>
  <label>
    <input type="radio" name="mode" value="ticker">
    <span><strong>Singolo ticker</strong><br>
    <span class="desc">Scraping di un singolo ticker per simbolo o nome.</span></span>
  </label>
  <div id="tick-extra" class="mode-extra">
    <div class="ticker-search">
      <input id="ticker-input" class="ticker-input"
             placeholder="Cerca simbolo o nome..." disabled>
      <div id="ticker-results" class="ticker-results"></div>
    </div>
  </div>
</div>
<button id="run-btn" class="run-btn" type="button">▶ Avvia</button>
"""

_RUN_SCRIPT = """\
(function () {
  var btn = document.getElementById("run-btn");
  var output = document.getElementById("output");
  var statusBar = document.getElementById("status-bar");
  var pollTimer = null;
  var catExtra = document.getElementById("cat-extra");
  var catSelect = document.getElementById("category-select");
  var catCount = document.getElementById("cat-count");
  var tickExtra = document.getElementById("tick-extra");
  var tickerInput = document.getElementById("ticker-input");
  var tickerResults = document.getElementById("ticker-results");
  var allTickers = {};
  var selectedCat = null;
  var selectedSym = null;

  /* --- Load tickers on page load --- */
  fetch("/api/tickers").then(function (r) { return r.json(); }).then(function (d) {
    allTickers = d.tickers || {};
    Object.keys(allTickers).sort().forEach(function (cat) {
      var opt = document.createElement("option");
      opt.value = cat;
      opt.textContent = cat + " (" + allTickers[cat].length + " ticker)";
      catSelect.appendChild(opt);
    });
  });

  /* --- Radio change → show/hide extra UI --- */
  document.querySelectorAll('input[name="mode"]').forEach(function (r) {
    r.addEventListener("change", function () {
      var m = this.value;
      catExtra.classList.toggle("visible", m === "category");
      tickExtra.classList.toggle("visible", m === "ticker");
      catSelect.disabled = (m !== "category");
      tickerInput.disabled = (m !== "ticker");
      if (m !== "ticker") { tickerResults.classList.remove("open"); tickerResults.innerHTML = ""; selectedSym = null; }
      if (m !== "category") { selectedCat = null; catCount.textContent = ""; }
    });
  });

  /* --- Category select --- */
  catSelect.addEventListener("change", function () {
    selectedCat = this.value || null;
    var n = selectedCat ? (allTickers[selectedCat] || []).length : 0;
    catCount.textContent = selectedCat ? n + " ticker" : "";
  });

  /* --- Ticker search --- */
  tickerInput.addEventListener("input", function () {
    var q = this.value.trim().toLowerCase();
    if (!q) { tickerResults.classList.remove("open"); return; }
    var hits = [];
    Object.keys(allTickers).forEach(function (cat) {
      allTickers[cat].forEach(function (t) {
        if (t.symbol.toLowerCase().indexOf(q) !== -1 ||
            t.name.toLowerCase().indexOf(q) !== -1) {
          hits.push({s: t.symbol, n: t.name, c: cat});
        }
      });
    });
    if (!hits.length) { tickerResults.innerHTML = '<div class="ticker-result-item" style="color:var(--muted)">Nessun risultato</div>'; tickerResults.classList.add("open"); return; }
    tickerResults.innerHTML = hits.slice(0, 20).map(function (h) {
      return '<div class="ticker-result-item" data-sym="' + h.s + '">'
        + '<span class="sym">' + h.s + '</span> &ndash; ' + h.n
        + ' <span class="cat">(' + h.c + ')</span></div>';
    }).join("");
    tickerResults.classList.add("open");
  });
  tickerInput.addEventListener("blur", function () {
    setTimeout(function () { tickerResults.classList.remove("open"); }, 150);
  });
  tickerResults.addEventListener("click", function (e) {
    var el = e.target.closest(".ticker-result-item");
    if (!el || !el.dataset.sym) return;
    selectedSym = el.dataset.sym;
    tickerInput.value = selectedSym;
    tickerResults.classList.remove("open");
  });

  /* --- Status check on load --- */
  fetch("/api/scraper-run/status").then(function (r) { return r.json(); }).then(function (s) {
    if (s.running) {
      btn.disabled = true; btn.textContent = "⏳ In corso...";
      statusBar.className = "status-bar running";
      statusBar.textContent = "Scraping in corso (pid " + s.pid + ")...";
      startPoll();
    } else if (s.exit_code !== null) {
      var ok = s.exit_code === 0;
      statusBar.className = "status-bar " + (ok ? "done" : "error");
      statusBar.textContent = ok ? "Ultimo scrape completato" : "Ultimo scrape fallito (exit " + s.exit_code + ")";
    }
  });

  function startPoll() {
    if (pollTimer) return;
    pollTimer = setInterval(function () {
      fetch("/api/scraper-run/status").then(function (r) { return r.json(); }).then(function (s) {
        if (!s.running) {
          clearInterval(pollTimer); pollTimer = null;
          btn.disabled = false; btn.textContent = "▶ Avvia";
          var ok = s.exit_code === 0;
          statusBar.className = "status-bar " + (ok ? "done" : "error");
          statusBar.textContent = ok ? "Scrape completato" : "Scrape fallito (exit " + s.exit_code + ")";
        }
      });
    }, 2000);
  }

  /* --- Run button --- */
  btn.addEventListener("click", function () {
    var mode = document.querySelector('input[name="mode"]:checked').value;
    if (mode === "category" && !selectedCat) { alert("Seleziona una categoria"); return; }
    if (mode === "ticker" && !selectedSym) { alert("Seleziona un ticker"); return; }

    var url = "/api/scraper-run?mode=" + encodeURIComponent(mode);
    if (mode === "category") url += "&category=" + encodeURIComponent(selectedCat);
    if (mode === "ticker") url += "&ticker=" + encodeURIComponent(selectedSym);

    btn.disabled = true; btn.textContent = "⏳ In corso...";
    output.textContent = "";
    statusBar.className = "status-bar running";
    statusBar.textContent = "Scraping in corso...";

    var evtSource = new EventSource(url);
    evtSource.onmessage = function (e) {
      output.textContent += e.data + "\\n";
      output.scrollTop = output.scrollHeight;
    };
    evtSource.addEventListener("done", function (e) {
      evtSource.close();
      btn.disabled = false; btn.textContent = "▶ Avvia";
      var code = parseInt(e.data, 10);
      var ok = code === 0;
      statusBar.className = "status-bar " + (ok ? "done" : "error");
      statusBar.textContent = ok ? "Scrape completato" : "Scrape fallito (exit " + code + ")";
    });
    evtSource.onerror = function () {
      evtSource.close();
      btn.disabled = false; btn.textContent = "▶ Avvia";
      output.textContent += "\\n❌ Errore di connessione";
    };
  });

  /* --- Clear button --- */
  document.getElementById("clear-btn").addEventListener("click", function () {
    output.textContent = "";
  });
})();
"""


def render_scraper_run_page() -> str:
    """Render the scraper-run launch page."""
    header = render_header("scraper-run", "\U0001f680 Esecuzione scraping",
                           "Lancia la pipeline di scraping dal browser")
    content = (
        f'<div class="run-card">{_MODE_OPTIONS}</div>'
        '<div id="status-bar" class="status-bar"></div>'
        '<div class="output-card">'
        '<div class="output-header"><span>Output</span>'
        '<button id="clear-btn" class="clear-btn" type="button">\u2715 Pulisci</button></div>'
        '<pre id="output"></pre>'
        "</div>"
    )
    return wrap_page(
        "Esecuzione scraping", "scraper-run", _SCRAPER_RUN_CSS, header, content,
        scripts=f"{_SHARED_SCRIPT}<script>{_RUN_SCRIPT}</script>",
    )
