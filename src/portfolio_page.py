"""Portfolio page generator.

Builds a static HTML page for viewing positions, SELL signals,
transactions and adding new trades.  All data comes from the API —
zero client-side calculations.
"""

from __future__ import annotations

from report_html import _CSS
from report_helpers import FAVICON_LINK, render_nav

_PAGE_CSS = _CSS + """\
.card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 16px; margin-top: 20px; }
.card h2 { margin: 0 0 12px 0; font-size: 1rem; color: var(--text); }
.summary-grid { display: flex; gap: 16px; flex-wrap: wrap; }
.summary-item { flex: 1; min-width: 140px; }
.summary-label { font-size: 0.8rem; color: var(--muted); }
.summary-value { font-size: 1.3rem; font-weight: 700; }
.summary-value.positive { color: var(--green); }
.summary-value.negative { color: var(--red); }
.summary-value.neutral { color: var(--text); }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
th { text-align: center; padding: 8px 6px; border-bottom: 2px solid var(--border);
     color: var(--muted); font-weight: 600; font-size: 0.8rem; }
td { padding: 8px 6px; border-bottom: 1px solid var(--border); color: var(--text);
     text-align: center; }
td:first-child, th:first-child { text-align: left; }
tr:hover td { background: var(--bg); }
.pnl-pos { color: var(--green); font-weight: 600; }
.pnl-neg { color: var(--red); font-weight: 600; }
.empty-msg { color: var(--muted); font-style: italic; padding: 16px 0; }
.sell-badge { display: inline-block; padding: 2px 8px; border-radius: 6px;
              font-size: 0.75rem; font-weight: 600; }
.sell-NESSUNA { background: var(--bg); color: var(--muted); }
.sell-MANTIENI { background: #1a3a1a; color: #4ade80; }
.sell-PRENDI { background: #3a2a0a; color: #fbbf24; }
.sell-RIDUCI { background: #3a1a1a; color: #f87171; }
.sell-ATTENZIONE { background: #2a1a3a; color: #c084fc; }
.sell-reasons { font-size: 0.78rem; color: var(--muted); margin-top: 4px; }
.sell-note { font-size: 0.78rem; color: var(--text); margin-top: 2px; font-style: italic; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.form-grid label { display: flex; flex-direction: column; font-size: 0.85rem;
        color: var(--muted); }
.form-grid input, .form-grid select, .form-grid textarea {
        background: var(--bg); color: var(--text); border: 1px solid var(--border);
        border-radius: 6px; padding: 6px 8px; font-size: 0.9rem; margin-top: 2px; }
.form-grid textarea { resize: vertical; min-height: 36px; }
.form-actions { margin-top: 12px; display: flex; gap: 8px; }
.btn { border: none; border-radius: 8px; padding: 8px 16px; cursor: pointer;
        font-size: 0.9rem; font-weight: 600; }
.btn-primary { background: var(--green); color: #fff; }
.btn-primary:hover { opacity: 0.9; }
.btn-secondary { background: var(--border); color: var(--text); }
.btn-secondary:hover { opacity: 0.8; }
.btn-danger { background: var(--red); color: #fff; font-size: 0.8rem;
        padding: 4px 10px; }
.btn-danger:hover { opacity: 0.8; }
.btn-edit { background: var(--yellow); color: #000; font-size: 0.8rem;
        padding: 4px 10px; }
.btn-edit:hover { opacity: 0.8; }
.status-msg { margin-top: 8px; padding: 6px 10px; border-radius: 6px;
        font-size: 0.85rem; display: none; }
.status-msg.ok { display: block; background: var(--green); color: #fff; }
.status-msg.err { display: block; background: var(--red); color: #fff; }
.warn-banner { background: var(--yellow); color: #000; padding: 8px 16px;
        border-radius: 8px; margin-top: 12px; font-size: 0.85rem;
        font-weight: 600; display: none; }
.warn-banner.visible { display: block; }
"""

_FORM_HTML = """\
<div class="card" id="form-card">
  <h2 id="form-title">Nuova transazione</h2>
  <div class="form-grid">
    <label>Data <input type="date" id="f-date" required></label>
    <label>Ticker <input type="text" id="f-ticker" placeholder="NVDA" required></label>
    <label>Azione
      <select id="f-action">
        <option value="BUY">BUY</option>
        <option value="SELL">SELL</option>
      </select>
    </label>
    <label>Quantità <input type="number" id="f-qty" step="any" min="0.01" required></label>
    <label>Prezzo USD <input type="number" id="f-price" step="any" min="0" required></label>
    <label>Commissione USD <input type="number" id="f-comm" step="any" min="0" value="0"></label>
    <label>Note <textarea id="f-note" rows="1"></textarea></label>
  </div>
  <div class="form-actions">
    <button class="btn btn-primary" id="f-submit">Salva</button>
    <button class="btn btn-secondary" id="f-cancel" style="display:none">Annulla</button>
  </div>
  <div class="status-msg" id="f-status"></div>
</div>
"""


def render_portfolio_page() -> str:
    """Return the full HTML for the portfolio page."""
    return f"""\
<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Portfolio — scraper-system</title>
  {FAVICON_LINK}
  <style>{_PAGE_CSS}</style>
</head>
<body>
  <div class="container">
  <header>
    <div>{render_nav("portfolio")} </div>
    <h1>Portfolio</h1>
    <p class="subtitle">Transazioni, posizioni e P/L</p>
  </header>

  <main>
    <!-- Summary -->
    <div class="card" id="summary-card">
      <h2>Riepilogo</h2>
      <div class="summary-grid" id="summary-grid">
        <div class="summary-item"><div class="summary-label">Posizioni aperte</div>
          <div class="summary-value neutral" id="s-count">—</div></div>
        <div class="summary-item"><div class="summary-label">Valore corrente</div>
          <div class="summary-value neutral" id="s-value">—</div></div>
        <div class="summary-item"><div class="summary-label">Capitale investito</div>
          <div class="summary-value neutral" id="s-cost">—</div></div>
        <div class="summary-item"><div class="summary-label">P/L non realizzato</div>
          <div class="summary-value neutral" id="s-unrealized">—</div></div>
        <div class="summary-item"><div class="summary-label">P/L realizzato</div>
          <div class="summary-value neutral" id="s-realized">—</div></div>
        <div class="summary-item"><div class="summary-label">P/L totale</div>
          <div class="summary-value neutral" id="s-total">—</div></div>
      </div>
      <div class="warn-banner" id="price-warning">
        ⚠️ Alcuni prezzi correnti non disponibili — P/L parziale.
      </div>
    </div>

    <!-- Open positions -->
    <div class="card">
      <h2>Posizioni aperte</h2>
      <div id="positions-body">
        <table>
          <thead><tr>
            <th>Ticker</th><th>Qtà</th><th>Prezzo medio</th><th>Ultimo prezzo</th>
            <th>Valore</th><th>Costo</th><th>Gain/Loss $</th><th>Gain/Loss %</th>
          </tr></thead>
          <tbody id="positions-tbody"></tbody>
        </table>
        <div class="empty-msg" id="positions-empty">Nessuna posizione aperta.</div>
      </div>
    </div>

    <!-- SELL signals -->
    <div class="card">
      <h2>Segnali SELL</h2>
      <div id="sell-body">
        <div id="sell-list"></div>
        <div class="empty-msg" id="sell-empty">Nessun segnale disponibile.</div>
      </div>
    </div>

    <!-- Transactions -->
    <div class="card">
      <h2>Transazioni</h2>
      <div id="transactions-body">
        <table>
          <thead><tr>
            <th>Data</th><th>Ticker</th><th>Azione</th><th>Qtà</th>
            <th>Prezzo</th><th>Comm.</th><th>Note</th><th>Azioni</th>
          </tr></thead>
          <tbody id="transactions-tbody"></tbody>
        </table>
        <div class="empty-msg" id="transactions-empty">Nessuna transazione registrata.</div>
      </div>
    </div>

    {_FORM_HTML}
  </main>
  </div>

  <script>{_PAGE_SCRIPT}</script>
</body>
</html>"""


_PAGE_SCRIPT = """\
(function () {
  /* ── State ──────────────────────────────────────────────────────── */
  var editingId = null;

  /* ── Helpers ────────────────────────────────────────────────────── */
  function $(id) { return document.getElementById(id); }
  function fmt(v) {
    if (v == null) return '—';
    return v.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  }
  function pnlClass(v) {
    if (v == null) return 'neutral';
    return v >= 0 ? 'pnl-pos' : 'pnl-neg';
  }
  function valClass(v) {
    if (v == null) return 'neutral';
    return v >= 0 ? 'positive' : 'negative';
  }
  function fmtDate(iso) {
    if (!iso) return '—';
    var p = iso.split('-');
    return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : iso;
  }

  function api(method, path, body) {
    var opts = {method: method, headers: {'Content-Type': 'application/json'}};
    if (body) opts.body = JSON.stringify(body);
    return fetch(path, opts).then(function (r) {
      return r.json().then(function (d) { return {status: r.status, data: d}; });
    });
  }

  /* ── Load data ──────────────────────────────────────────────────── */
  function loadAll() {
    loadPositions();
    loadTransactions();
    loadSellSignals();
  }

  function loadPositions() {
    api('GET', '/api/positions').then(function (r) {
      var d = r.data;
      if (!d.ok) return;
      renderSummary(d);
      renderPositions(d.positions || []);
    });
  }

  function loadTransactions() {
    api('GET', '/api/transactions').then(function (r) {
      var d = r.data;
      if (!d.ok) return;
      renderTransactions(d.transactions || []);
    });
  }

  function loadSellSignals() {
    api('GET', '/api/portfolio/evaluate').then(function (r) {
      var d = r.data;
      if (!d.ok) return;
      renderSellSignals(d.evaluations || []);
    });
  }

  function renderSellSignals(list) {
    var container = $('sell-list');
    var empty = $('sell-empty');
    if (!list.length) { container.innerHTML = ''; empty.style.display = ''; return; }
    empty.style.display = 'none';
    container.innerHTML = list.map(function (ev) {
      var badgeClass = 'sell-' + ev.sell_signal.split(' ')[0];
      var reasons = (ev.reasons || []).map(function (r) { return '• ' + r; }).join('<br>');
      return '<div style="margin-bottom:12px;padding:10px;border:1px solid var(--border);border-radius:8px;">'
        + '<div style="display:flex;align-items:center;gap:10px;">'
        + '<strong>' + ev.ticker + '</strong> '
        + '<span class="sell-badge ' + badgeClass + '">' + ev.sell_signal + '</span>'
        + '<span style="font-size:0.75rem;color:var(--muted);">confidenza: ' + ev.confidence + '</span>'
        + '</div>'
        + (reasons ? '<div class="sell-reasons">' + reasons + '</div>' : '')
        + (ev.suggested_action_note ? '<div class="sell-note">→ ' + ev.suggested_action_note + '</div>' : '')
        + '</div>';
    }).join('');
  }

  /* ── Render summary ─────────────────────────────────────────────── */
  function renderSummary(d) {
    var pos = d.positions || [];
    var realized = d.realized_pnl_by_ticker || {};
    var totalRealized = 0;
    Object.keys(realized).forEach(function (k) { totalRealized += realized[k]; });

    var totalCost = 0, totalValue = 0, hasMissing = false;
    pos.forEach(function (p) {
      totalCost += (p.total_cost_usd || 0);
      if (p.market_value_usd != null) {
        totalValue += p.market_value_usd;
      } else {
        hasMissing = true;
      }
    });
    var unrealized = totalValue - totalCost;
    var totalPnl = totalRealized + (hasMissing ? null : unrealized);

    $('s-count').textContent = pos.length;
    $('s-cost').textContent = '$' + fmt(totalCost);
    $('s-cost').className = 'summary-value neutral';

    if (!hasMissing) {
      $('s-value').textContent = '$' + fmt(totalValue);
      $('s-value').className = 'summary-value ' + valClass(unrealized);
      $('s-unrealized').textContent = '$' + fmt(unrealized);
      $('s-unrealized').className = 'summary-value ' + valClass(unrealized);
    } else {
      $('s-value').textContent = 'parziale';
      $('s-value').className = 'summary-value neutral';
      $('s-unrealized').textContent = '—';
      $('s-unrealized').className = 'summary-value neutral';
    }

    $('s-realized').textContent = '$' + fmt(totalRealized);
    $('s-realized').className = 'summary-value ' + valClass(totalRealized);

    if (totalPnl != null) {
      $('s-total').textContent = '$' + fmt(totalPnl);
      $('s-total').className = 'summary-value ' + valClass(totalPnl);
    } else {
      $('s-total').textContent = 'parziale';
      $('s-total').className = 'summary-value neutral';
    }

    $('price-warning').classList.toggle('visible', hasMissing);
  }

  /* ── Render positions ───────────────────────────────────────────── */
  function renderPositions(list) {
    var tbody = $('positions-tbody');
    var empty = $('positions-empty');
    if (!list.length) { tbody.innerHTML = ''; empty.style.display = ''; return; }
    empty.style.display = 'none';
    tbody.innerHTML = list.map(function (p) {
      var gain = p.unrealized_pnl_usd;
      var pct = p.unrealized_pnl_pct;
      return '<tr>'
        + '<td><strong>' + p.ticker + '</strong></td>'
        + '<td>' + fmt(p.quantity) + '</td>'
        + '<td>$' + fmt(p.average_entry_price_usd) + '</td>'
        + '<td>' + (p.market_price_usd != null ? '$' + fmt(p.market_price_usd) : '—') + '</td>'
        + '<td>' + (p.market_value_usd != null ? '$' + fmt(p.market_value_usd) : '—') + '</td>'
        + '<td>$' + fmt(p.total_cost_usd) + '</td>'
        + '<td class="' + pnlClass(gain) + '">$' + fmt(gain) + '</td>'
        + '<td class="' + pnlClass(pct) + '">' + (pct != null ? fmt(pct) + '%' : '—') + '</td>'
        + '</tr>';
    }).join('');
  }

  /* ── Render transactions ────────────────────────────────────────── */
  function renderTransactions(list) {
    var tbody = $('transactions-tbody');
    var empty = $('transactions-empty');
    if (!list.length) { tbody.innerHTML = ''; empty.style.display = ''; return; }
    empty.style.display = 'none';
    tbody.innerHTML = list.map(function (t) {
      var actionClass = t.action === 'BUY' ? 'pnl-pos' : 'pnl-neg';
      return '<tr>'
        + '<td>' + fmtDate(t.trade_date) + '</td>'
        + '<td><strong>' + t.ticker + '</strong></td>'
        + '<td class="' + actionClass + '">' + t.action + '</td>'
        + '<td>' + fmt(t.quantity) + '</td>'
        + '<td>$' + fmt(t.price_usd) + '</td>'
        + '<td>$' + fmt(t.commission_usd) + '</td>'
        + '<td>' + (t.note || '') + '</td>'
        + '<td>'
        + '<button class="btn btn-edit" data-id="' + t.id + '">modifica</button> '
        + '<button class="btn btn-danger" data-id="' + t.id + '">elimina</button>'
        + '</td></tr>';
    }).join('');
  }

  /* ── Form ───────────────────────────────────────────────────────── */
  function clearForm() {
    $('f-date').value = '';
    $('f-ticker').value = '';
    $('f-action').value = 'BUY';
    $('f-qty').value = '';
    $('f-price').value = '';
    $('f-comm').value = '0';
    $('f-note').value = '';
    $('f-status').className = 'status-msg';
    $('f-status').textContent = '';
    editingId = null;
    $('form-title').textContent = 'Nuova transazione';
    $('f-cancel').style.display = 'none';
  }

  function fillForm(t) {
    $('f-date').value = t.trade_date;
    $('f-ticker').value = t.ticker;
    $('f-action').value = t.action;
    $('f-qty').value = t.quantity;
    $('f-price').value = t.price_usd;
    $('f-comm').value = t.commission_usd;
    $('f-note').value = t.note || '';
    editingId = t.id;
    $('form-title').textContent = 'Modifica transazione #' + t.id;
    $('f-cancel').style.display = '';
    $('f-date').focus();
  }

  function submitForm() {
    var payload = {
      trade_date: $('f-date').value,
      ticker: $('f-ticker').value.trim().toUpperCase(),
      action: $('f-action').value,
      quantity: parseFloat($('f-qty').value),
      price_usd: parseFloat($('f-price').value),
      commission_usd: parseFloat($('f-comm').value) || 0,
      note: $('f-note').value.trim() || null,
    };
    if (!payload.trade_date || !payload.ticker || isNaN(payload.quantity) || isNaN(payload.price_usd)) {
      showStatus('f-status', true, 'Compila tutti i campi obbligatori');
      return;
    }
    var method = editingId ? 'PUT' : 'POST';
    var path = editingId ? '/api/transactions/' + editingId : '/api/transactions';
    api(method, path, payload).then(function (r) {
      if (r.data.ok) {
        showStatus('f-status', false, editingId ? 'Aggiornato' : 'Aggiunto');
        clearForm();
        loadAll();
      } else {
        showStatus('f-status', true, r.data.message || 'Errore');
      }
    }).catch(function () {
      showStatus('f-status', true, 'Errore di connessione');
    });
  }

  function showStatus(id, isErr, msg) {
    var el = $(id);
    el.className = 'status-msg ' + (isErr ? 'err' : 'ok');
    el.textContent = msg;
  }

  function deleteTx(id) {
    if (!confirm('Eliminare la transazione #' + id + '?')) return;
    api('DELETE', '/api/transactions/' + id).then(function (r) {
      if (r.data.ok) loadAll();
      else alert(r.data.message || 'Errore');
    });
  }

  /* ── Events ─────────────────────────────────────────────────────── */
  $('f-submit').addEventListener('click', submitForm);
  $('f-cancel').addEventListener('click', function () { clearForm(); loadAll(); });

  $('transactions-tbody').addEventListener('click', function (e) {
    var btn = e.target.closest('button');
    if (!btn) return;
    var id = parseInt(btn.dataset.id, 10);
    if (btn.classList.contains('btn-danger')) {
      deleteTx(id);
    } else if (btn.classList.contains('btn-edit')) {
      api('GET', '/api/transactions/' + id).then(function (r) {
        if (r.data.ok) fillForm(r.data.transaction);
      });
    }
  });

  /* ── Init ───────────────────────────────────────────────────────── */
  /* Set today as default date */
  $('f-date').value = new Date().toISOString().slice(0, 10);
  loadAll();
})();
"""
