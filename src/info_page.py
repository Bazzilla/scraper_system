"""Info/status page — system data overview + import/export.

Shows status of databases (record counts, sizes) and files (size, last
modified).  Below the status section: import/export for tickers,
portfolio transactions, and valuation history.
"""

from __future__ import annotations

from page_base import _SHARED_SCRIPT, render_header, wrap_page

_INFO_CSS = """\
.status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        gap: 16px; margin-top: 20px; }
.status-card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 16px; }
.status-card h3 { margin: 0 0 12px; font-size: 1rem; }
.status-row { display: flex; justify-content: space-between; padding: 6px 0;
        border-bottom: 1px solid var(--border); font-size: 0.9rem; }
.status-row:last-child { border-bottom: none; }
.status-label { color: var(--muted); }
.status-value { font-weight: 600; }
.status-value.missing { color: var(--red); }
.status-badge { display: inline-block; padding: 2px 8px; border-radius: 6px;
        font-size: 0.75rem; font-weight: 600; }
.badge-ok { background: var(--green); color: #fff; }
.badge-warn { background: var(--yellow); color: #000; }
.badge-err { background: var(--red); color: #fff; }
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
.refresh-btn { background: var(--card); color: var(--text); border: 1px solid var(--border);
        border-radius: 8px; padding: 6px 12px; font-size: 0.85rem; cursor: pointer; }
"""

_INFO_SCRIPT = """\
(function () {
  var output = document.getElementById("output");

  /* ── Helpers ────────────────────────────────────────────────────── */
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
      fetch(url, { method: "POST", headers: {"Content-Type": "application/json"}, body: e.target.result })
        .then(function (r) { return r.json(); })
        .then(function (d) { callback(null, d); })
        .catch(function (err) { callback(err); });
    };
    reader.readAsText(file);
  }

  /* ── Status load ────────────────────────────────────────────────── */
  function loadStatus() {
    document.getElementById("status-body").innerHTML = '<span class="line-info">Caricamento...</span>';
    fetch("/api/status").then(function (r) { return r.json(); }).then(function (d) {
      var html = "";
      /* Databases */
      html += '<div class="status-card"><h3>Database</h3>';
      ["portfolio", "valuation_history", "scraper_audit"].forEach(function (name) {
        var db = (d.databases || {})[name] || {};
        var rows = db.rows || 0;
        var size = db.size_human || "—";
        var exists = db.exists;
        var cls = exists ? "" : " missing";
        html += '<div class="status-row"><span class="status-label">' + name + '</span>'
          + '<span class="status-value' + cls + '">' + (exists ? rows + " righe · " + size : "non trovato") + '</span></div>';
      });
      html += '</div>';
      /* Files */
      html += '<div class="status-card"><h3>File</h3>';
      ["config", "output_json", "report_html", "manual_overrides", "indicator_registry"].forEach(function (name) {
        var f = (d.files || {})[name] || {};
        var size = f.size_human || "—";
        var exists = f.exists;
        var cls = exists ? "" : " missing";
        var modified = exists ? new Date(f.modified).toLocaleDateString("it-IT") : "";
        html += '<div class="status-row"><span class="status-label">' + name + '</span>'
          + '<span class="status-value' + cls + '">' + (exists ? size + " · " + modified : "non trovato") + '</span></div>';
      });
      html += '</div>';
      document.getElementById("status-body").innerHTML = html;
    }).catch(function (e) {
      document.getElementById("status-body").innerHTML = '<span class="line-err">Errore: ' + e + '</span>';
    });
  }
  loadStatus();
  document.getElementById("refresh-btn").addEventListener("click", loadStatus);

  /* ── Ticker export/import ───────────────────────────────────────── */
  document.getElementById("export-tickers").addEventListener("click", function () {
    clearOutput();
    fetch("/api/tickers/export").then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) { appendLine("Errore: " + (d.message || ""), "line-err"); return; }
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
    appendLine("File: " + file.name, "line-info");
    uploadJson("/api/tickers/import", file, function (err, d) {
      if (err) { appendLine("Errore: " + err, "line-err"); return; }
      if (!d.ok) { appendLine("Errore: " + (d.message || ""), "line-err"); return; }
      (d.imported || []).forEach(function (t) { appendLine("+ " + t.symbol + " -> " + t.category, "line-ok"); });
      (d.skipped || []).forEach(function (t) { appendLine("~ " + t.symbol + ": " + t.reason, "line-warn"); });
      (d.conflicts || []).forEach(function (t) { appendLine("x " + t.symbol + ": esiste in '" + t.existing_category + "'", "line-err"); });
      appendLine("Riepilogo: " + (d.imported||[]).length + " importati, " + (d.skipped||[]).length + " saltati, " + (d.conflicts||[]).length + " conflitti", "line-ok");
    });
  });

  /* ── Portfolio export/import ────────────────────────────────────── */
  document.getElementById("export-portfolio").addEventListener("click", function () {
    clearOutput();
    fetch("/api/portfolio/export").then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) { appendLine("Errore: " + (d.message || ""), "line-err"); return; }
      downloadJson(d, "portfolio-export.json");
      appendLine("OK: " + (d.transactions || []).length + " transazioni", "line-ok");
    }).catch(function (e) { appendLine("Errore: " + e, "line-err"); });
  });

  document.getElementById("import-portfolio-btn").addEventListener("click", function () {
    var file = document.getElementById("import-portfolio-file").files[0];
    if (!file) { alert("Seleziona un file JSON"); return; }
    clearOutput();
    appendLine("File: " + file.name, "line-info");
    uploadJson("/api/portfolio/import", file, function (err, d) {
      if (err) { appendLine("Errore: " + err, "line-err"); return; }
      if (!d.ok) { appendLine("Errore: " + (d.message || ""), "line-err"); return; }
      appendLine("Importate: " + d.imported + " | Saltate: " + d.skipped, "line-ok");
    });
  });

  /* ── Valuation export/import ────────────────────────────────────── */
  document.getElementById("export-valuation").addEventListener("click", function () {
    clearOutput();
    fetch("/api/valuation/export").then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) { appendLine("Errore: " + (d.message || ""), "line-err"); return; }
      downloadJson(d, "valuation-export.json");
      appendLine("OK: " + (d.snapshots || []).length + " snapshot", "line-ok");
    }).catch(function (e) { appendLine("Errore: " + e, "line-err"); });
  });

  document.getElementById("import-valuation-btn").addEventListener("click", function () {
    var file = document.getElementById("import-valuation-file").files[0];
    if (!file) { alert("Seleziona un file JSON"); return; }
    clearOutput();
    appendLine("File: " + file.name, "line-info");
    uploadJson("/api/valuation/import", file, function (err, d) {
      if (err) { appendLine("Errore: " + err, "line-err"); return; }
      if (!d.ok) { appendLine("Errore: " + (d.message || ""), "line-err"); return; }
      appendLine("Importati: " + d.imported + " | Saltati: " + d.skipped, "line-ok");
    });
  });

  /* ── Clear ──────────────────────────────────────────────────────── */
  document.getElementById("clear-btn").addEventListener("click", clearOutput);
})();
"""


def render_info_page() -> str:
    """Render the info/status page."""
    header = render_header("info", "\u2139\ufe0f Info",
                           "Stato del sistema e import/export dati")
    content = (
        # ── Status ──────────────────────────────────────────────────
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:20px">'
        "<h2 style=\"margin:0\">Stato sistema</h2>"
        '<button id="refresh-btn" class="refresh-btn" type="button">'
        "\U0001f504 Aggiorna</button></div>"
        '<div id="status-body" class="status-grid">'
        '<span class="line-info">Caricamento...</span>'
        "</div>"
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
        # ── Portfolio ───────────────────────────────────────────────
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
        # ── Valuation ───────────────────────────────────────────────
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
        "Info", "info", _INFO_CSS, header, content,
        scripts=f"{_SHARED_SCRIPT}<script>{_INFO_SCRIPT}</script>",
    )
