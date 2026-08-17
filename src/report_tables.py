"""Ticker tables, indicator matrix and stale summary for the HTML report."""

from __future__ import annotations

import html as html_mod
from typing import Any

from report_helpers import (
    _age_attrs,
    _sema,
    _signal_badge,
    _status_badge,
    compute_signal,
    fmt,
    format_iso_dt,
    market_regime,
)


def render_ticker_table(
    category: str,
    entries: dict[str, Any],
    regime: str = "neutral",
) -> str:
    """Render one sector's ticker table with indicator semaphores."""
    rows: list[str] = []
    for symbol in sorted(entries):
        entry = entries[symbol]
        ind = entry
        rows.append(
            f"<tr{_age_attrs(ind.get('fetched_at'), ind.get('stale_after_hours'))}>"
            f'<td><span class="ticker">{html_mod.escape(symbol)}</span>'
            f'<br><span class="name">{html_mod.escape(entry.get("name", ""))}</span></td>'
            f"<td>{_sema(ind.get('last_close'), 'close')}</td>"
            f"<td>{_sema(ind.get('rsi_14'), 'rsi')}</td>"
            f"<td>{_sema(ind.get('mfi_14'), 'mfi')}</td>"
            f"<td>{fmt(ind.get('obv'))}</td>"
            f"<td>{fmt(ind.get('sma_50'))}</td>"
            f"<td>{fmt(ind.get('sma_200'))}</td>"
            f"<td>{_sema(ind.get('drawdown_52w'), 'drawdown')}</td>"
            f"<td>{_signal_badge(compute_signal(ind, regime))}</td>"
            f'<td>{format_iso_dt(ind.get("fetched_at"))}</td>'
            "</tr>"
        )
    header = (
        "<thead><tr>"
        "<th>Ticker</th><th>Close</th><th>RSI</th><th>MFI</th><th>OBV</th>"
        "<th>SMA50</th><th>SMA200</th><th>Drawdown</th><th>Segnale</th><th>Aggiornato</th>"
        "</tr></thead>"
    )
    return f"<table>{header}<tbody>{''.join(rows)}</tbody></table>"


def render_indicator_matrix(indicators_data: dict[str, Any] | None) -> str:
    """Render the strategy-indicator coverage matrix.

    Shows, per strategy indicator: name, implementation_status
    (implemented/proxy/missing/manual_supported), coverage (belongs to the
    strategy — static), availability (data really available at runtime),
    usable_in_strategy_score (coherent AND available, or accepted proxy),
    runtime source (scraped/manual/missing), semantic coherence, source and
    notes.
    """
    matrix = indicators_data or {}
    indicators = {
        k: v for k, v in matrix.items() if isinstance(v, dict) and k not in ("_meta", "summary")
    }
    if not indicators:
        return ""
    rows: list[str] = []
    for key in sorted(indicators):
        ind = indicators[key]
        impl = ind.get("implementation_status", "missing")
        coverage = ind.get("coverage", False)
        availability = ind.get("availability", False)
        usable = ind.get("usable_in_strategy_score", False)
        sema = "✅" if ind.get("semantic_coherent") else "❌"
        source = ind.get("primary_source") or "—"
        source_runtime = ind.get("source", "missing")
        source_badge = _status_badge(source_runtime)
        notes = html_mod.escape(str(ind.get("notes", "")))
        rows.append(
            "<tr>"
            f'<td><strong>{html_mod.escape(str(ind.get("name", key)))}</strong>'
            f'<br><span class="name">{html_mod.escape(str(ind.get("strategy_ref", "")))}</span></td>'
            f"<td>{_status_badge(impl)}</td>"
            f"<td>{'✅ sì' if coverage else '❌ no'}</td>"
            f"<td>{'✅ sì' if availability else '❌ no'}</td>"
            f"<td>{'✅ sì' if usable else '❌ no'}</td>"
            f"<td>{source_badge}</td>"
            f"<td>{sema}</td>"
            f"<td>{html_mod.escape(source)}</td>"
            f"<td>{notes}</td>"
            "</tr>"
        )
    header = (
        "<thead><tr>"
        "<th>Indicatore</th><th>Implementation</th><th>Coverage</th><th>Availability</th>"
        "<th>Usabile nello score</th><th>Provenienza</th><th>Semantica coerente</th>"
        "<th>Fonte primaria</th><th>Note</th>"
        "</tr></thead>"
    )
    return (
        "<div class='indicator-matrix'>"
        "<h2>Stato indicatori strategia</h2>"
        "<p class='sub'>"
        "<strong>Coverage</strong> = l'indicatore APPARTIENE alla strategia "
        "(statico, dalle specifiche — true anche se non implementato).<br>"
        "<strong>Implementation</strong> = implemented · proxy · missing · "
        "manual_supported (statico).<br>"
        "<strong>Availability</strong> = disponibile davvero a runtime · "
        "<strong>Usabile nello score</strong> = coverage E disponibile E "
        "implementabile (o proxy esplicitamente accettato) · "
        "<strong>Provenienza</strong> = scraped | manual | missing.</p>"
        f"<table>{header}<tbody>{''.join(rows)}</tbody></table>"
        "</div>"
    )


def render_stale_summary(summary: dict[str, Any]) -> str:
    """Render the stale/error summary footer."""
    details = summary.get("stale_details", [])
    details_html = ""
    if details:
        items = "".join(f"<li>{html_mod.escape(str(d))}</li>" for d in details)
        details_html = f"<ul>{items}</ul>"
    errors = summary.get("errors", 0)
    error_note = (
        f' <strong class="badge stale">⚠️ {errors} errore/i</strong>'
        if errors
        else ""
    )
    return (
        "<footer>"
        f"<strong>Stato sorgenti:</strong> "
        f"{summary.get('fresh', 0)}/{summary.get('total_sources', 0)} fresh · "
        f"{summary.get('stale', 0)} stale · "
        f"affidabilità: {summary.get('signal_reliability', '—')}"
        f"{error_note}"
        f"{details_html}"
        "</footer>"
    )


def _ticker_sections(data: dict[str, Any]) -> str:
    """Render per-category ticker tables merging ohlcv (close) + indicators."""
    indicators = data.get("indicators", {})
    ohlcv = data.get("ohlcv", {})
    if not indicators and not ohlcv:
        return ""
    sections: list[str] = []

    regime = market_regime(data.get("fgi", {}).get("score"))

    def _categories(mapping: dict[str, Any]) -> set[str]:
        # Solo le chiavi il cui valore è un dict rappresentano categorie
        # (esclude la chiave "status" a livello modulo).
        return {k for k, v in mapping.items() if isinstance(v, dict)}

    all_categories = sorted(_categories(indicators) | _categories(ohlcv))
    for category in all_categories:
        ind_entries = indicators.get(category, {})
        ohlcv_entries = ohlcv.get(category, {})
        # merge: last_close da ohlcv, indicatori da indicators.
        # Solo le voci che sono dict rappresentano ticker (esclude "status").
        # NB: .get() senza default — se "status" esiste in una sola mappa,
        # per l'altra restituisce None (non {}) ed evita falsi ticker.
        symbols = {
            symbol
            for symbol in set(ind_entries) | set(ohlcv_entries)
            if isinstance(ind_entries.get(symbol), dict)
            or isinstance(ohlcv_entries.get(symbol), dict)
        }
        merged: dict[str, Any] = {}
        for symbol in symbols:
            base = dict(ohlcv_entries.get(symbol, {})) if isinstance(ohlcv_entries.get(symbol), dict) else {}
            ind = ind_entries.get(symbol, {})
            if isinstance(ind, dict):
                base.update(ind)
            merged[symbol] = base
        if not merged:
            continue
        display = category.upper()
        sections.append(f"<h2>{html_mod.escape(display)} ({len(merged)})</h2>")
        sections.append(render_ticker_table(category, merged, regime=regime))
    return "".join(sections)
