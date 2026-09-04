"""Data exchange page generator — import/export ticker lists.

Builds a static HTML page for exporting the full ticker list as JSON
and importing a JSON/YAML file with conflict detection. Output is
displayed inline (imported/skipped/conflicts) without server-side files.
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
  var importBtn = document.getElementById("import-btn");
  var fileInput = document.getElementById("file-input");

  function appendLine(text, cls) {
    var span = document.createElement("span");
    span.className = cls || "";
    span.textContent = text + "\\n";
    output.appendChild(span);
    output.scrollTop = output.scrollHeight;
  }

  function clearOutput() { output.textContent = ""; }

  /* --- Export --- */
  document.getElementById("export-btn").addEventListener("click", function () {
    clearOutput();
    appendLine("Esportazione in corso...", "line-info");
    fetch("/api/tickers/export").then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) { appendLine("Errore: " + (d.message || "sconosciuto"), "line-err"); return; }
      var blob = new Blob([JSON.stringify(d, null, 2)], {type: "application/json"});
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url; a.download = "tickers-export.json";
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
      var cats = Object.keys(d.tickers || {});
      var count = cats.reduce(function (n, c) { return n + (d.tickers[c] || []).length; }, 0);
      appendLine("Export completato: " + count + " ticker in " + cats.length + " categorie.", "line-ok");
      appendLine("File scaricato: tickers-export.json", "line-info");
    }).catch(function (e) { appendLine("Errore di rete: " + e, "line-err"); });
  });

  /* --- Import --- */
  importBtn.addEventListener("click", function () {
    var file = fileInput.files[0];
    if (!file) { alert("Seleziona un file JSON o YAML"); return; }
    clearOutput();
    appendLine("Lettura file: " + file.name + " (" + (file.size / 1024).toFixed(1) + " KB)", "line-info");
    var reader = new FileReader();
    reader.onload = function (e) {
      var content = e.target.result;
      var isYaml = file.name.endsWith(".yaml") || file.name.endsWith(".yml");
      var contentType = isYaml ? "application/yaml" : "application/json";
      appendLine("Import in corso...", "line-info");
      fetch("/api/tickers/import", {
        method: "POST",
        headers: {"Content-Type": contentType},
        body: content
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (!d.ok) { appendLine("Errore: " + (d.message || "sconosciuto"), "line-err"); return; }
        (d.imported || []).forEach(function (t) {
          appendLine("+ " + t.symbol + " -> " + t.category, "line-ok");
        });
        (d.skipped || []).forEach(function (t) {
          appendLine("~ " + t.symbol + " (" + t.category + "): " + t.reason, "line-warn");
        });
        (d.conflicts || []).forEach(function (t) {
          appendLine("x " + t.symbol + ": esiste gia' in '" + t.existing_category
            + "', richiesto in '" + t.import_category + "'", "line-err");
        });
        appendLine("", "");
        var sum = (d.imported || []).length;
        var skip = (d.skipped || []).length;
        var conf = (d.conflicts || []).length;
        appendLine("Riepilogo: " + sum + " importati, " + skip + " saltati, " + conf + " conflitti", "line-ok");
      }).catch(function (err) { appendLine("Errore di rete: " + err, "line-err"); });
    };
    reader.readAsText(file);
  });

  /* --- Clear --- */
  document.getElementById("clear-btn").addEventListener("click", clearOutput);
})();
"""


def render_data_exchange_page() -> str:
    """Render the data import/export page."""
    header = render_header("data-exchange", "\U0001f504 Import/Export",
                           "Esporta e importa l'elenco dei ticker")
    content = (
        '<div class="exchange-card">'
        "<h2>Esporta ticker</h2>"
        '<div class="exchange-row">'
        '<button id="export-btn" class="btn btn-export" type="button">'
        "\U0001f4e5 Scarica JSON</button>"
        '<span class="line-info" style="font-size:0.85rem">'
        "Esporta l'elenco completo di ticker e categorie</span>"
        "</div></div>"
        '<div class="exchange-card">'
        "<h2>Importa ticker</h2>"
        '<div class="exchange-row">'
        "<div><label>File JSON o YAML</label>"
        '<input id="file-input" type="file" accept=".json,.yaml,.yml"></div>'
        '<button id="import-btn" class="btn btn-import" type="button">'
        "\U0001f4e4 Importa</button>"
        "</div></div>"
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
