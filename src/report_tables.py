"""Ticker tables, indicator matrix and stale summary for the HTML report."""

from __future__ import annotations

import html as html_mod
from typing import Any

from report_helpers import (
    GATE_CLOSED,
    GATE_MISSING_OR_STALE,
    GATE_OPEN,
    GATE_STRONG_OPEN,
    GATE_WATCH_ONLY,
    _age_attrs,
    _collapsible,
    _sema,
    _signal_badge,
    attrattiva_score,
    _status_badge,
    buy_signal_reasons,
    buy_the_dip_gate,
    compute_signal,
    fmt,
    format_iso_dt,
    market_regime,
)
from valuation_store import bucket_label
from page_base import render_ticker


_TIER_ORDER = {"core": 0, "secondary": 1, "opportunistic": 2}

# Chiavi meta del modulo valuation da NON fondere nella riga ticker:
# fetched_at/stale_after_hours/status della riga devono restare quelli degli
# indicatori tecnici (badge di età), non quelli dello snapshot valutazione.
_VALUATION_META_KEYS = {"symbol", "name", "fetched_at", "frequency",
                        "stale_after_hours", "status"}


def _merge_valuation(merged: dict[str, Any], val_entries: dict[str, Any]) -> None:
    """Merge valuation fields (upside, multiples) into the merged rows."""
    for symbol, entry in val_entries.items():
        if not isinstance(entry, dict) or symbol not in merged:
            continue
        for key, value in entry.items():
            if key not in _VALUATION_META_KEYS:
                merged[symbol][key] = value


def _merge_category_entries(
    ind_entries: Any,
    ohlcv_entries: Any,
    val_entries: Any,
) -> dict[str, Any]:
    """Merge one category's ohlcv (close) + indicators + valuation rows.

    ``last_close`` comes from ohlcv, technical indicators from indicators,
    valuation fields (upside, multiples) are display-only overlays. Only
    dict values represent tickers (excludes module-level "status" keys).
    """
    ind = ind_entries if isinstance(ind_entries, dict) else {}
    ohlcv = ohlcv_entries if isinstance(ohlcv_entries, dict) else {}
    val = val_entries if isinstance(val_entries, dict) else {}
    symbols = {
        symbol
        for symbol in set(ind) | set(ohlcv)
        if isinstance(ind.get(symbol), dict) or isinstance(ohlcv.get(symbol), dict)
    }
    merged: dict[str, Any] = {}
    for symbol in symbols:
        base = dict(ohlcv.get(symbol, {})) if isinstance(ohlcv.get(symbol), dict) else {}
        ind_entry = ind.get(symbol, {})
        if isinstance(ind_entry, dict):
            base.update(ind_entry)
        merged[symbol] = base
    _merge_valuation(merged, val)
    return merged


def collect_merged_tickers(data: dict[str, Any]) -> dict[str, Any]:
    """All tickers merged across categories: symbol → entry.

    Each entry carries the source category under ``_category`` for display
    in cross-section summaries (e.g. the buy-signals Markdown).
    """
    indicators = data.get("indicators", {})
    ohlcv = data.get("ohlcv", {})
    valuation = data.get("valuation", {})

    def _categories(mapping: dict[str, Any]) -> set[str]:
        # Solo le chiavi il cui valore è un dict rappresentano categorie.
        return {k for k, v in mapping.items() if isinstance(v, dict)}

    result: dict[str, Any] = {}
    for category in sorted(
        _categories(indicators) | _categories(ohlcv) | _categories(valuation)
    ):
        merged = _merge_category_entries(
            indicators.get(category),
            ohlcv.get(category),
            valuation.get(category),
        )
        for symbol, entry in merged.items():
            entry = dict(entry)
            entry["_category"] = category
            result[symbol] = entry
    return result


def _bucket_title(ind: dict[str, Any]) -> str:
    """Tooltip con il bucket descrittivo del fair value (validation-mode)."""
    bucket = ind.get("bucket")
    label = bucket_label(bucket)
    if not label:
        return ""
    return f' title="Fair value: {html_mod.escape(label)}"'


def _tier_sort_key(symbol: str, meta: dict[str, Any] | None) -> tuple[int, str]:
    """Sort key: quality_tier first (core < secondary < opportunistic), then symbol."""
    tier = (meta or {}).get("quality_tier", "")
    rank = _TIER_ORDER.get(tier, 3)  # unknown/absent tiers sort last
    return (rank, symbol)


def _ticker_meta_line(meta: dict[str, Any] | None) -> str:
    """Render the strategic metadata line under the ticker name (display-only)."""
    if not meta:
        return ""
    parts: list[str] = []
    tier = meta.get("quality_tier")
    if tier:
        parts.append(f"<span class='meta-tier'>{html_mod.escape(tier)}</span>")
    validity = meta.get("buy_the_dip_validity")
    if validity:
        parts.append(f"<span class='meta-validity'>{html_mod.escape(validity)}</span>")
    role = meta.get("strategy_role")
    if role:
        parts.append(f"<span class='meta-role'>{html_mod.escape(role)}</span>")
    notes = meta.get("notes")
    if notes:
        parts.append(f"<span class='meta-notes'>{html_mod.escape(notes)}</span>")
    if not parts:
        return ""
    return f"<br><span class='ticker-meta'>{' · '.join(parts)}</span>"


def render_ticker_table(
    category: str,
    entries: dict[str, Any],
    regime: str = "neutral",
    fgi_score: float | None = None,
    tickers_meta: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Render one sector's ticker table with indicator semaphores.

    ``tickers_meta`` maps symbol → strategic metadata (quality_tier,
    strategy_role, buy_the_dip_validity, notes). Metadata is DISPLAY-ONLY:
    it never influences the signal (the FGI Buy-the-Dip gate is the only
    operational gate). Rows are sorted by quality_tier (core first), then
    alphabetically; without metadata the order is purely alphabetical.

    Ogni cella porta ``data-value`` machine-readable e ogni colonna
    ``data-type`` (text|num|date): il JS lato client li usa per
    ordinamento ciclico e filtri (vedi report_html._SCRIPT).
    """
    rows: list[str] = []
    meta = tickers_meta or {}
    for symbol in sorted(entries, key=lambda s: _tier_sort_key(s, meta.get(s))):
        entry = entries[symbol]
        ind = entry
        signal = compute_signal(ind, regime, fgi_score=fgi_score)
        score = attrattiva_score(ind, fgi_score=fgi_score, regime=regime)

        def _dv(value: Any) -> str:
            """Machine-readable cell value ('' quando assente)."""
            return html_mod.escape("" if value is None else str(value))

        rows.append(
            f"<tr{_age_attrs(ind.get('fetched_at'), ind.get('stale_after_hours'))}>"
            f'<td data-value="{_dv(symbol)}">{render_ticker(symbol, meta.get(symbol))}'
            f'<br><span class="name">{html_mod.escape(entry.get("name", ""))}</span>'
            f"{_ticker_meta_line(meta.get(symbol))}</td>"
            f"<td data-value=\"{_dv(ind.get('last_close'))}\">{_sema(ind.get('last_close'), 'close')}</td>"
            f"<td data-value=\"{_dv(ind.get('rsi_14'))}\">{_sema(ind.get('rsi_14'), 'rsi')}</td>"
            f"<td data-value=\"{_dv(ind.get('mfi_14'))}\">{_sema(ind.get('mfi_14'), 'mfi')}</td>"
            f"<td data-value=\"{_dv(ind.get('obv'))}\">{fmt(ind.get('obv'))}</td>"
            f"<td data-value=\"{_dv(ind.get('sma_50'))}\">{fmt(ind.get('sma_50'))}</td>"
            f"<td data-value=\"{_dv(ind.get('sma_200'))}\">{fmt(ind.get('sma_200'))}</td>"
            f"<td data-value=\"{_dv(ind.get('drawdown_52w'))}\">{_sema(ind.get('drawdown_52w'), 'drawdown')}</td>"
            f"<td data-value=\"{_dv(ind.get('upside_pct'))}\""
            f"{_bucket_title(ind)}>{_sema(ind.get('upside_pct'), 'upside')}</td>"
            f'<td data-value="{score}" title="Attrattiva buy-the-dip (0-100): '
            f'punteggio sintetico ordinabile">{score}</td>'
            f'<td data-value="{signal}">{_signal_badge(signal)}</td>'
            f'<td data-value="{_dv(ind.get("fetched_at"))}">{format_iso_dt(ind.get("fetched_at"))}</td>'
            "</tr>"
        )
    header = (
        "<thead><tr>"
        '<th data-type="text">Ticker</th>'
        '<th data-type="num">Close</th>'
        '<th data-type="num">RSI</th>'
        '<th data-type="num">MFI</th>'
        '<th data-type="num">OBV</th>'
        '<th data-type="num">SMA50</th>'
        '<th data-type="num">SMA200</th>'
        '<th data-type="num">Drawdown</th>'
        '<th data-type="num" title="Upside vs target mediano analisti (fair value, informativo)">Upside FV</th>'
        '<th data-type="num" title="Attrattiva buy-the-dip (0-100): punteggio sintetico '
        'ordinabile — dal più al meno papabile">Attrattiva</th>'
        '<th data-type="text">Segnale</th>'
        '<th data-type="date">Aggiornato</th>'
        "</tr></thead>"
    )
    return f'<table class="ticker-table">{header}<tbody>{"".join(rows)}</tbody></table>'


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
    return _collapsible(
        "Stato indicatori strategia",
        (
            "<div class='indicator-matrix'>"
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
        ),
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


def _ticker_sections(data: dict[str, Any], tickers_config: dict[str, Any] | None = None) -> str:
    """Render per-category ticker tables merging ohlcv (close) + indicators.

    ``tickers_config`` is the normalized ``tickers`` section from config.yaml
    (category → list of {symbol, name, quality_tier, ...}). It is used ONLY
    for display metadata and tier ordering — never as a signal.
    """
    indicators = data.get("indicators", {})
    ohlcv = data.get("ohlcv", {})
    valuation = data.get("valuation", {})
    if not indicators and not ohlcv:
        return ""
    sections: list[str] = []

    # Build symbol → metadata map from the config tickers section.
    tickers_meta: dict[str, dict[str, Any]] = {}
    for entries in (tickers_config or {}).values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("symbol"):
                tickers_meta[entry["symbol"]] = entry

    regime = market_regime(data.get("fgi", {}).get("score"))
    # Buy-the-Dip FGI gate: il punteggio FGI è usabile solo se fresh.
    # Se mancante/stale → None → compute_signal fa fail-closed (no BUY).
    fgi = data.get("fgi", {})
    fgi_score = fgi.get("score") if fgi.get("status") == "fresh" else None

    def _categories(mapping: dict[str, Any]) -> set[str]:
        # Solo le chiavi il cui valore è un dict rappresentano categorie
        # (esclude la chiave "status" a livello modulo).
        return {k for k, v in mapping.items() if isinstance(v, dict)}

    all_categories = sorted(
        _categories(indicators) | _categories(ohlcv) | _categories(valuation)
    )
    for category in all_categories:
        # merge: last_close da ohlcv, indicatori da indicators, valuation
        # display-only. NB: .get() senza default — se "status" esiste in una
        # sola mappa, per l'altra restituisce None (non {}) ed evita falsi
        # ticker (gestito da _merge_category_entries).
        merged = _merge_category_entries(
            indicators.get(category),
            ohlcv.get(category),
            valuation.get(category),
        )
        if not merged:
            continue
        display = category.upper()
        sections.append(_collapsible(
            f"{html_mod.escape(display)} ({len(merged)})",
            render_ticker_table(
                category, merged, regime=regime, fgi_score=fgi_score,
                tickers_meta=tickers_meta,
            ),
        ))
    return "".join(sections)


def build_buy_signals_markdown(data: dict[str, Any]) -> str:
    """Markdown summary of VALUTA INGRESSO tickers (copy-to-clipboard).

    Returns ``""`` when no ticker currently has the buy signal. Values and
    motivations mirror the signal pipeline (``compute_signal`` + buy-the-dip
    FGI gate): this is a copy of the report state, not a new decision layer.
    """
    fgi = data.get("fgi", {})
    fgi_score = fgi.get("score") if fgi.get("status") == "fresh" else None
    regime = market_regime(fgi.get("score"))

    buys = [
        (symbol, entry)
        for symbol, entry in collect_merged_tickers(data).items()
        if compute_signal(entry, regime, fgi_score=fgi_score) == "buy"
    ]
    if not buys:
        return ""

    # Ordine: Attrattiva decrescente (le più papabili prima), poi simbolo.
    buys.sort(
        key=lambda pair: (
            -attrattiva_score(pair[1], fgi_score=fgi_score, regime=regime),
            pair[0],
        )
    )

    gate = buy_the_dip_gate(fgi_score)
    gate_labels = {
        GATE_STRONG_OPEN: "aperto (paura estrema)",
        GATE_OPEN: "aperto (paura sufficiente)",
        GATE_WATCH_ONLY: "solo osservazione",
        GATE_CLOSED: "chiuso",
        GATE_MISSING_OR_STALE: "mancante/stale (fail-closed)",
    }
    fgi_str = f"{fgi_score:.0f}" if fgi_score is not None else "—"

    def _cell(text: Any) -> str:
        """Markdown table cell: escape pipes, collapse newlines."""
        return str(text).replace("|", "\\|").replace("\n", " ")

    def _num(value: Any, spec: str = ".2f") -> str:
        return "—" if value is None else format(value, spec)

    def _pct(value: Any) -> str:
        return "—" if value is None else f"{value:.1f}%"

    def _vs(price: Any, sma: Any) -> str:
        if price is None or sma is None:
            return "—"
        return "sopra" if price >= sma else "sotto"

    lines = [
        f"## 🎯 Segnali VALUTA INGRESSO — {len(buys)} ticker",
        "",
        f"Contesto: FGI {fgi_str} (gate {gate_labels.get(gate, gate)}) · "
        f"regime {regime} · generato {format_iso_dt(data.get('generated_at'))}",
        "",
        "| Ticker | Settore | Close | RSI | MFI | vs SMA50 | vs SMA200 "
        "| Drawdown | Upside FV | Attrattiva |",
        "|---|---|---:|---:|---:|:-:|:-:|---:|---:|---:|",
    ]
    for symbol, entry in buys:
        score = attrattiva_score(entry, fgi_score=fgi_score, regime=regime)
        lines.append(
            f"| **{symbol}** | {_cell(str(entry.get('_category', '')).upper())} "
            f"| {_num(entry.get('last_close'))} "
            f"| {_num(entry.get('rsi_14'), '.1f')} "
            f"| {_num(entry.get('mfi_14'), '.1f')} "
            f"| {_vs(entry.get('last_close'), entry.get('sma_50'))} "
            f"| {_vs(entry.get('last_close'), entry.get('sma_200'))} "
            f"| {_pct(entry.get('drawdown_52w'))} "
            f"| {_pct(entry.get('upside_pct'))} "
            f"| **{score}** |"
        )

    lines += ["", "### Perché VALUTA INGRESSO", ""]
    for symbol, entry in buys:
        score = attrattiva_score(entry, fgi_score=fgi_score, regime=regime)
        name = entry.get("name") or symbol
        category = str(entry.get("_category", "")).upper()
        lines.append(f"- **{symbol}** ({name}, {category}) — Attrattiva {score}")
        for reason in buy_signal_reasons(entry, fgi_score):
            lines.append(f"  - {reason}")

    lines += [
        "",
        "*Setup da valutare con le conferme della strategia — non un consiglio "
        "di acquisto automatico (gate FGI + conferme obbligatorie).*",
    ]
    return "\n".join(lines)


def render_buy_signals_section(data: dict[str, Any]) -> str:
    """Collapsible section with the copyable Markdown buy-signals summary."""
    md = build_buy_signals_markdown(data)
    if not md:
        body = (
            '<p class="md-empty">Nessun ticker con segnale '
            "<strong>VALUTA INGRESSO</strong> al momento: gate FGI non aperto "
            "e/o condizioni tecniche non soddisfatte.</p>"
        )
    else:
        body = (
            '<div class="md-toolbar">'
            '<button type="button" class="subtle" id="copy-buy-signals">'
            "📋 Copia Markdown</button></div>"
            f'<pre class="md-box" id="buy-signals-md">{html_mod.escape(md)}</pre>'
        )
    return _collapsible("🎯 Sintesi VALUTA INGRESSO (Markdown)", body)
