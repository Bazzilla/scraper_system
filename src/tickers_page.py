"""Ticker lists editor page generator.

Builds a static HTML page (same styles as the dashboard) that lets the user
manage the ``tickers`` section of config.yaml:

- add/remove tickers within a category
- rename categories
- add/remove whole categories

The page embeds the current mapping as JSON; edits happen client-side on a
JS model (event delegation, no inline handlers) and are persisted with a
single "Salva" action posting to ``POST /api/tickers/save``
(overrides_server.py), which validates, backs up the previous YAML
(epoch-named copy under ``backups/``) and re-renders the report.
"""

from __future__ import annotations

import json
from typing import Any

from report_html import _CSS, _SCRIPT

_PAGE_CSS = _CSS + """\
.category-card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 16px; margin-bottom: 16px; }
.category-head { display: flex; align-items: center; gap: 10px;
        flex-wrap: wrap; margin-bottom: 10px; }
.category-head input.cat-name { background: var(--bg); color: var(--text);
        border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px;
        font-size: 1rem; font-weight: 700; width: 220px; }
.category-head .count { color: var(--muted); font-size: 0.85rem; }
.ticker-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
        padding: 4px 0; border-bottom: 1px solid var(--border); }
.ticker-row:last-of-type { border-bottom: none; }
input.txt { background: var(--bg); color: var(--text);
        border: 1px solid var(--border); border-radius: 6px;
        padding: 5px 8px; font-size: 0.9rem; }
input.sym { width: 90px; font-weight: 700; text-transform: uppercase; }
input.nm { width: 240px; }
button { cursor: pointer; border: none; border-radius: 8px; padding: 6px 12px;
        font-size: 0.85rem; font-weight: 600; }
button.primary { background: var(--green); color: #fff; }
button.danger { background: var(--red); color: #fff; }
button.subtle { background: var(--bg); color: var(--text);
        border: 1px solid var(--border); }
.add-row { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.toolbar { display: flex; align-items: center; gap: 12px; margin: 16px 0;
        flex-wrap: wrap; }
.toolbar input.txt { padding: 6px 8px; }
.msg { padding: 8px 12px; border-radius: 8px; font-size: 0.9rem; }
.msg.ok { background: var(--green); color: #fff; }
.msg.err { background: var(--red); color: #fff; }
"""

# Editor JS: modello lato client + event delegation (nessun handler inline).
_EDITOR_SCRIPT = """\
<script>
(function () {
  var model = JSON.parse(document.getElementById("tickers-data").textContent);
  var listEl = document.getElementById("categories");
  var msgEl = document.getElementById("msg");

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function findSymbol(symbol) {
    var upper = symbol.toUpperCase();
    var cats = Object.keys(model);
    for (var i = 0; i < cats.length; i++) {
      var entries = model[cats[i]];
      for (var j = 0; j < entries.length; j++) {
        if (entries[j].symbol.toUpperCase() === upper) return cats[i];
      }
    }
    return null;
  }

  function render() {
    var html = "";
    Object.keys(model).forEach(function (cat) {
      var entries = model[cat];
      html += '<div class="category-card" data-cat="' + esc(cat) + '">';
      html += '<div class="category-head">'
        + '<label>Nome categoria <input class="txt cat-name" data-cat="' + esc(cat)
        + '" value="' + esc(cat) + '"></label>'
        + '<span class="count">' + entries.length + ' ticker</span>'
        + '<button type="button" class="danger" data-action="remove-category"'
        + ' data-cat="' + esc(cat) + '">Elimina categoria</button></div>';
      entries.forEach(function (t, i) {
        html += '<div class="ticker-row">'
          + '<input class="txt sym" value="' + esc(t.symbol) + '" readonly>'
          + '<input class="txt nm" data-action="rename-ticker" data-cat="' + esc(cat)
          + '" data-index="' + i + '" value="' + esc(t.name) + '">'
          + '<button type="button" class="subtle" data-action="remove-ticker"'
          + ' data-cat="' + esc(cat) + '" data-index="' + i + '">✕ rimuovi</button>'
          + '</div>';
      });
      html += '<div class="add-row">'
        + '<input class="txt sym" data-new-sym="' + esc(cat) + '" placeholder="SYMBOL">'
        + '<input class="txt nm" data-new-name="' + esc(cat) + '" placeholder="Nome società">'
        + '<button type="button" class="primary" data-action="add-ticker"'
        + ' data-cat="' + esc(cat) + '">+ Aggiungi</button></div>';
      html += '</div>';
    });
    listEl.innerHTML = html;
  }

  function renameCategory(input, oldName) {
    var newName = input.value.trim();
    if (!newName || newName === oldName) { render(); return; }
    if (Object.prototype.hasOwnProperty.call(model, newName)) {
      alert("Categoria già esistente: " + newName);
      render(); return;
    }
    var ordered = {};
    Object.keys(model).forEach(function (cat) {
      ordered[cat === oldName ? newName : cat] = model[cat];
    });
    model = ordered;
    render();
  }

  window.addEventListener("change", function (ev) {
    var el = ev.target;
    if (el.classList && el.classList.contains("cat-name")) {
      renameCategory(el, el.getAttribute("data-cat"));
      return;
    }
    if (el.getAttribute && el.getAttribute("data-action") === "rename-ticker") {
      var name = el.value.trim();
      if (!name) { alert("Il nome non può essere vuoto"); render(); return; }
      model[el.getAttribute("data-cat")][+el.getAttribute("data-index")].name = name;
    }
  });

  listEl.addEventListener("click", function (ev) {
    var btn = ev.target.closest("button[data-action]");
    if (!btn) return;
    var action = btn.getAttribute("data-action");
    var cat = btn.getAttribute("data-cat");
    if (action === "remove-ticker") {
      if (model[cat].length <= 1) {
        alert("Ogni categoria deve avere almeno un ticker: "
          + "elimina l'intera categoria o aggiungine un altro.");
        return;
      }
      model[cat].splice(+btn.getAttribute("data-index"), 1);
      render();
      return;
    }
    if (action === "remove-category") {
      if (!confirm("Eliminare la categoria '" + cat + "' con "
          + model[cat].length + " ticker?")) return;
      delete model[cat];
      render();
      return;
    }
    if (action === "add-ticker") {
      var symInput = listEl.querySelector('[data-new-sym="' + cat + '"]');
      var nameInput = listEl.querySelector('[data-new-name="' + cat + '"]');
      var symbol = symInput.value.trim().toUpperCase();
      var name = nameInput.value.trim();
      if (!symbol || !name) { alert("Symbol e nome sono obbligatori"); return; }
      var owner = findSymbol(symbol);
      if (owner) { alert("Symbol già presente in '" + owner + "': " + symbol); return; }
      model[cat].push({ symbol: symbol, name: name });
      render();
    }
  });

  document.getElementById("add-category-btn").addEventListener("click", function () {
    var input = document.getElementById("new-category");
    var name = input.value.trim().toLowerCase().replace(/\\s+/g, "_");
    if (!name) { alert("Nome categoria obbligatorio"); return; }
    if (Object.prototype.hasOwnProperty.call(model, name)) {
      alert("Categoria già esistente: " + name); return;
    }
    model[name] = [];
    input.value = "";
    render();
    var symInput = listEl.querySelector('[data-new-sym="' + name + '"]');
    if (symInput) symInput.focus();
  });

  document.getElementById("save-btn").addEventListener("click", function () {
    for (var cat in model) {
      if (!model[cat].length) {
        alert("La categoria '" + cat + "' è vuota: aggiungi un ticker o eliminala.");
        return;
      }
    }
    var btn = this;
    btn.disabled = true;
    msgEl.className = "msg";
    msgEl.textContent = "Salvataggio in corso...";
    fetch("/api/tickers/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tickers: model })
    }).then(function (resp) { return resp.json(); }).then(function (data) {
      msgEl.className = "msg " + (data.ok ? "ok" : "err");
      msgEl.textContent = data.message || (data.ok ? "Salvato" : "Errore");
      btn.disabled = false;
    }).catch(function () {
      msgEl.className = "msg err";
      msgEl.textContent = "Errore di rete";
      btn.disabled = false;
    });
  });

  render();
})();
</script>
"""


def render_tickers_page(tickers: dict[str, Any]) -> str:
    """Render the complete tickers editor page."""
    payload = json.dumps(tickers, ensure_ascii=False).replace("</", "<\\/")
    return (
        "<!DOCTYPE html>\n<html lang=\"it\" data-theme=\"dark\">\n<head>"
        "<meta charset=\"utf-8\">"
        "<title>Gestione ticker</title>"
        f"<style>{_PAGE_CSS}</style>"
        "</head>\n<body><div class=\"container\">"
        "<header>"
        "<div><h1>📋 Gestione ticker</h1>"
        '<div class="sub">Categorie e liste persistenti su config.yaml '
        "(ogni salvataggio crea un backup datato in backups/)</div></div>"
        '<div><a href="/report.html" class="badge fresh">Vai al report →</a> '
        '<a href="/overrides.html" class="badge fresh">✍️ Indicatori</a> '
        '<button id="theme-toggle" type="button">☀️ Light</button></div>'
        "</header>"
        '<div class="toolbar">'
        '<button id="save-btn" type="button" class="primary">💾 Salva su config.yaml</button>'
        '<input id="new-category" class="txt" placeholder="nuova-categoria">'
        '<button id="add-category-btn" type="button" class="subtle">+ Nuova categoria</button>'
        '<span id="msg" role="status"></span>'
        "</div>"
        f'<script id="tickers-data" type="application/json">{payload}</script>'
        '<div id="categories"></div>'
        "</div>"
        f"{_SCRIPT}"
        f"{_EDITOR_SCRIPT}"
        "</body>\n</html>"
    )
