"""Data exchange page generator — import/export tickers, portfolio, valuation.

Builds a static HTML page for exporting and importing:
- Ticker lists (JSON/YAML with conflict detection)
- Portfolio transactions (JSON)
- Valuation history snapshots (JSON)
"""

from __future__ import annotations

from page_base import _SHARED_SCRIPT, render_header, wrap_page

_DATA_EXCHANGE_CSS = """\
.exchange-card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 20px; margin-top: 20px; }
.exchange-card h2 { margin: 0 0 12px; font-size: 1.1rem; }
.exchange-row { display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-end; }
.exchange-row label { font-size: 0.85rem; color: var(--muted); display: block;
        margin-bottom: 4px; }
.exchange-row input[type="file"] { font-size: 0.9rem; }
.btn { padding: 8px 16px; border-radius: 8px; border: none; font-size: 0.9rem;
        font-weight: 600; cursor: pointer; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-export { background: var(--neutral); color: #fff; }
.btn-import { background: var(--green); color: #fff; }
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
        word-break: break-word; background: var(--bg); min-height: 80px; }
.line-ok { color: var(--green); }
.line-warn { color: var(--yellow); }
.line-err { color: var(--red); }
.line-info { color: var(--muted); }
"""

_EXCHANGE_SCRIPT = """\
(function () {
  var output = document.getElementById("output");

  function appendLine(text, cls) {
    var span = document.createElement("span");
    span.className = cls || "";
    span.textContent = text + "\\n";
    output.appendChild(span);
    output.scrollTop = output.scrollHeight;
  }

  function clearOutput() { output.textContent = ""; }

  function downloadJson(data, filename) {
    var blob = new Blob([JSON.stringify(data, null, 2)], {type: "application/json"});
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function uploadJson(url, file, callback) {
    var reader = new FileReader();
    reader.onload = function (e) {
      appendLine("Import in corso...", "line-info");
      fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: e.target.result
      }).then(function (r) { return r.json(); })
        .then(function (d) { callback(null, d); })
        .catch(function (err) { callback(err); });
    };
    reader.readAsText(file);
  }

  /* ── Ticker ──────────────────────────────────────────────────────── */
  document.getElementById("export-tickers").addEventListener("click", function () {
    clearOutput();
    appendLine("Esportazione ticker...", "line-info");
    fetch("/api/tickers/export").then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) { appendLine("Errore: " + (d.message || "sconosciuto"), "line-err"); return; }
      downloadJson(d, "tickers-export.json");
      var cats = Object.keys(d.tickers || {});
      var count = cats.reduce(function (n, c) { return n + (d.tickers[c] || []).length; }, 0);
      appendLine("OK: " + count + " ticker in " + cats.length + " categorie", "line-ok");
    }).catch(function (e) { appendLine("Errore: " + e, "line-err"); });
  });

  document.getElementById("import-tickers-btn").addEventListener("click", function () {
    var file = document.getElementById("import-tickers-file").files[0];
    if (!file) { alert("Seleziona un file JSON o YAML"); return; }
    clearOutput();
    appendLine("File: " + file.name + " (" + (file.size / 1024).toFixed(1) + " KB)", "line-info");
    uploadJson("/api/tickers/import", file, function (err, d) {
      if (err) { appendLine("Errore: " + err, "line-err"); return; }
      if (!d.ok) { appendLine("Errore: " + (d.message || "sconosciuto"), "line-err"); return; }
      (d.imported || []).forEach(function (t) { appendLine("+ " + t.symbol + " -> " + t.category, "line-ok"); });
      (d.skipped || []).forEach(function (t) { appendLine("~ " + t.symbol + ": " + t.reason, "line-warn"); });
      (d.conflicts || []).forEach(function (t) {
        appendLine("x " + t.symbol + ": esiste in '" + t.existing_category + "'", "line-err");
      });
      appendLine("Riepilogo: " + (d.imported||[]).length + " importati, " + (d.skipped||[]).length + " saltati, " + (d.conflicts||[]).length + " conflitti", "line-ok");
    });
  });

  /* ── Portfolio transactions ──────────────────────────────────────── */
  document.getElementById("export-portfolio").addEventListener("click", function () {
    clearOutput();
    appendLine("Esportazione transazioni...", "line-info");
    fetch("/api/portfolio/export").then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) { appendLine("Errore: " + (d.message || "sconosciuto"), "line-err"); return; }
      downloadJson(d, "portfolio-export.json");
      appendLine("OK: " + (d.transactions || []).length + " transazioni esportate", "line-ok");
    }).catch(function (e) { appendLine("Errore: " + e, "line-err"); });
  });

  document.getElementById("import-portfolio-btn").addEventListener("click", function () {
    var file = document.getElementById("import-portfolio-file").files[0];
    if (!file) { alert("Seleziona un file JSON"); return; }
    clearOutput();
    appendLine("File: " + file.name + " (" + (file.size / 1024).toFixed(1) + " KB)", "line-info");
    uploadJson("/api/portfolio/import", file, function (err, d) {
      if (err) { appendLine("Errore: " + err, "line-err"); return; }
      if (!d.ok) { appendLine("Errore: " + (d.message || "sconosciuto"), "line-err"); return; }
      appendLine("Importate: " + d.imported + " | Saltate: " + d.skipped, "line-ok");
    });
  });

  /* ── Valuation history ───────────────────────────────────────────── */
  document.getElementById("export-valuation").addEventListener("click", function () {
    clearOutput();
    appendLine("Esportazione valuation history...", "line-info");
    fetch("/api/valuation/export").then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) { appendLine("Errore: " + (d.message || "sconosciuto"), "line-err"); return; }
      downloadJson(d, "valuation-export.json");
      appendLine("OK: " + (d.snapshots || []).length + " snapshot esportati", "line-ok");
    }).catch(function (e) { appendLine("Errore: " + e, "line-err"); });
  });

  document.getElementById("import-valuation-btn").addEventListener("click", function () {
    var file = document.getElementById("import-valuation-file").files[0];
    if (!file) { alert("Seleziona un file JSON"); return; }
    clearOutput();
    appendLine("File: " + file.name + " (" + (file.size / 1024).toFixed(1) + " KB)", "line-info");
    uploadJson("/api/valuation/import", file, function (err, d) {
      if (err) { appendLine("Errore: " + err, "line-err"); return; }
      if (!d.ok) { appendLine("Errore: " + (d.message || "sconosciuto"), "line-err"); return; }
      appendLine("Importati: " + d.imported + " | Saltati: " + d.skipped, "line-ok");
    });
  });

  /* ── Clear ───────────────────────────────────────────────────────── */
  document.getElementById("clear-btn").addEventListener("click", clearOutput);
})();
"""


def render_data_exchange_page() -> str:
    """Render the data import/export page."""
    header = render_header("data-exchange", "\U0001f504 Import/Export",
                           "Esporta e importa dati di sistema")
    content = (
        # ── Ticker ──────────────────────────────────────────────────
        '<div class="exchange-card">'
        "<h2>\U0001f4cb Ticker</h2>"
        '<div class="exchange-row">'
        '<button id="export-tickers" class="btn btn-export" type="button">'
        "\U0001f4e5 Esporta JSON</button>"
        "<div><label>Importa da file</label>"
        '<input id="import-tickers-file" type="file" accept=".json,.yaml,.yml"></div>'
        '<button id="import-tickers-btn" class="btn btn-import" type="button">'
        "\U0001f4e4 Importa</button>"
        "</div></div>"
        # ── Portfolio transactions ──────────────────────────────────
        '<div class="exchange-card">'
        "<h2>\U0001f4b0 Transazioni portfolio</h2>"
        '<div class="exchange-row">'
        '<button id="export-portfolio" class="btn btn-export" type="button">'
        "\U0001f4e5 Esporta JSON</button>"
        "<div><label>Importa da file</label>"
        '<input id="import-portfolio-file" type="file" accept=".json"></div>'
        '<button id="import-portfolio-btn" class="btn btn-import" type="button">'
        "\U0001f4e4 Importa</button>"
        "</div></div>"
        # ── Valuation history ───────────────────────────────────────
        '<div class="exchange-card">'
        "<h2>\U0001f4ca Storico valuation</h2>"
        '<div class="exchange-row">'
        '<button id="export-valuation" class="btn btn-export" type="button">'
        "\U0001f4e5 Esporta JSON</button>"
        "<div><label>Importa da file</label>"
        '<input id="import-valuation-file" type="file" accept=".json"></div>'
        '<button id="import-valuation-btn" class="btn btn-import" type="button">'
        "\U0001f4e4 Importa</button>"
        "</div></div>"
        # ── Output ──────────────────────────────────────────────────
        '<div class="output-card">'
        '<div class="output-header"><span>Output</span>'
        '<button id="clear-btn" class="clear-btn" type="button">'
        "\u2715 Pulisci</button></div>"
        '<pre id="output"></pre>'
        "</div>"
    )
    return wrap_page(
        "Import/Export", "data-exchange", _DATA_EXCHANGE_CSS, header, content,
        scripts=f"{_SHARED_SCRIPT}<script>{_EXCHANGE_SCRIPT}</script>",
    )
