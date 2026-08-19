"""Market indicator cards for the HTML report generator."""

from __future__ import annotations

import html as html_mod
from typing import Any

from report_helpers import (
    _FGI_ZONES,
    _age_attrs,
    _fgi_rating_badge,
    fmt,
    format_iso_dt,
)


def render_market_cards(data: dict[str, Any]) -> str:
    """Render the market indicator cards (FGI, VIX, PCR, breadth, insider, AAII).

    Fail-closed rendering: a source whose status is "error" shows a clear
    error badge instead of silently rendering "—" (missing data is a signal).
    """
    parts: list[str] = []

    def _error_card(label: str, source: dict[str, Any]) -> str:
        error = str(source.get("error") or "dato non disponibile")
        return (
            '<div class="card"><div class="label">'
            f"{html_mod.escape(label)}</div>"
            '<div class="value">—</div>'
            f'<span class="badge stale">errore</span>'
            f'<div class="meta">{html_mod.escape(error[:80])}</div></div>'
        )

    def _origin_html(source: dict[str, Any]) -> str:
        """Render provenance: a 'manual' badge plus stale/note when relevant."""
        origin = source.get("origin")
        status = source.get("status")
        parts: list[str] = []
        if origin == "manual":
            parts.append('<span class="badge fresh">manual</span>')
        if status == "stale":
            parts.append('<span class="badge stale">stale</span>')
        if origin == "manual" and source.get("note"):
            note = html_mod.escape(str(source["note"]))
            parts.append(f'<span class="meta">📝 {note}</span>')
        return " ".join(parts) if parts else ""

    fgi = data.get("fgi", {})
    if fgi.get("status") == "error":
        parts.append(_error_card("CNN Fear &amp; Greed", fgi))
    else:
        fgi_score = fgi.get("score")
        fgi_zone = fgi.get("zone", "—")
        if fgi_score is not None:
            zone_cls = "greed"
            for threshold, name in _FGI_ZONES:
                if fgi_score < threshold:
                    zone_cls = name
                    break
            zone_badge = f'<span class="sema {zone_cls}">{html_mod.escape(fgi_zone)}</span>'
        else:
            zone_badge = ""
        fgi_source = fgi.get("source")
        source_html = f' · Fonte: {html_mod.escape(str(fgi_source))}' if fgi_source else ""
        fgi_components = fgi.get("fgi_components")
        if fgi_components:
            comp_rows = []
            for key, comp in fgi_components.items():
                name = key.replace("_", " ").title()
                score = comp.get("score")
                rating = str(comp.get("rating", ""))
                comp_rows.append(
                    '<div class="comp"><span class="comp-name">'
                    f"{html_mod.escape(name)}</span>"
                    f"<span>{fmt(score)} {_fgi_rating_badge(rating)}</span></div>"
                )
            components_html = f'<div class="fgi-components">{"".join(comp_rows)}</div>'
        else:
            components_html = ""
        parts.append(
            f'<div class="card"{_age_attrs(fgi.get("fetched_at"), fgi.get("stale_after_hours"))}><div class="label">CNN Fear &amp; Greed</div>'
            f'<div class="value">{fmt(fgi_score)}</div>{zone_badge}'
            f'<div class="meta">Aggiornato: {format_iso_dt(fgi.get("fetched_at"))}{source_html}</div>'
            f'{components_html}{_origin_html(fgi)}</div>'
        )

    vix = data.get("vix", {})
    vix_ts = data.get("vix_term_structure", {})
    vix_ok = vix.get("status") != "error" and vix.get("vix_close") is not None
    ts_ok = vix_ts.get("status") == "fresh" and vix_ts.get("m1") is not None

    if ts_ok:
        # F3/#10: il term structure (M1/M2) è l'indicatore strategico → è il
        # valore principale della card. VIX spot resta come nota informativa.
        structure = str(vix_ts.get("structure", ""))
        structure_cls = "fear" if structure == "backwardation" else "neutral"
        spot_note = (
            f' · VIX spot: {fmt(vix.get("vix_close"))} (info, non strategico)'
            if vix_ok else ""
        )
        parts.append(
            f'<div class="card"{_age_attrs(vix_ts.get("fetched_at"), vix_ts.get("stale_after_hours"))}>'
            f'<div class="label">VIX Term Structure '
            f'<span class="sema {structure_cls}">{html_mod.escape(structure)}</span></div>'
            f'<div class="value">M1 {fmt(vix_ts.get("m1"))} · M2 {fmt(vix_ts.get("m2"))}</div>'
            f'<div class="meta">Aggiornato: {format_iso_dt(vix_ts.get("fetched_at"))}'
            f'{spot_note}</div>'
            f'{_origin_html(vix_ts)}</div>'
        )
    elif vix_ok:
        # Fallback: senza term structure mostra VIX spot (proxy informativo).
        parts.append(
            f'<div class="card"{_age_attrs(vix.get("fetched_at"), vix.get("stale_after_hours"))}>'
            f'<div class="label">VIX Spot '
            '<span class="sema warning">proxy</span></div>'
            f'<div class="value">{fmt(vix.get("vix_close"))}</div>'
            f'<div class="meta">Aggiornato: {format_iso_dt(vix.get("fetched_at"))}'
            ' · term structure non disponibile</div></div>'
        )
    else:
        parts.append(_error_card("VIX Term Structure", vix_ts if vix_ts.get("status") == "error" else vix))

    pcr = data.get("pcr", {})
    if pcr.get("status") == "error":
        parts.append(_error_card("Equity Put/Call Ratio", pcr))
    else:
        equity_pcr = pcr.get("equity_pcr")
        pcr_cls = "fear" if equity_pcr is not None and equity_pcr >= 0.80 else (
            "greed" if equity_pcr is not None and equity_pcr <= 0.70 else "neutral")
        pcr_badge = "" if pcr_cls == "neutral" else (
            f'<span class="sema {pcr_cls}">{pcr_cls}</span>')
        parts.append(
            f'<div class="card"{_age_attrs(pcr.get("fetched_at"), pcr.get("stale_after_hours"))}><div class="label">Equity Put/Call Ratio</div>'
            f'<div class="value">{fmt(equity_pcr)}</div>{pcr_badge}'
            f'<div class="meta">Giorno: {pcr.get("trade_date", "—")} · '
            f'Aggiornato: {format_iso_dt(pcr.get("fetched_at"))}</div></div>'
        )

    pct_sma = data.get("pct_sma", {})
    if pct_sma.get("status") == "error":
        parts.append(_error_card("Breadth di mercato", pct_sma))
    elif pct_sma.get("pct_sma50") is not None or pct_sma.get("pct_sma200") is not None:
        # Valori manuali del MERCATO USA (F3/#13-14): pct_sma50/pct_sma200
        # sono al top level (formato manual override), non più nested in
        # "total" (il proxy locale sui 29 ticker è stato rimosso).
        p50 = pct_sma.get("pct_sma50")
        p200 = pct_sma.get("pct_sma200")

        def _breadth_sema(pct: float | None, threshold_low: float, threshold_mid: float) -> str:
            if pct is None:
                return ""
            cls = "fear" if pct < threshold_low else (
                "warning" if pct < threshold_mid else "ok")
            return f'<span class="sema {cls}">{cls}</span>'

        parts.append(
            f'<div class="card"{_age_attrs(pct_sma.get("fetched_at"), pct_sma.get("stale_after_hours"))}><div class="label">Breadth di mercato '
            '<span class="sema warning">manual</span></div>'
            f'<div class="value">SMA50 {fmt(p50)}% {_breadth_sema(p50, 20, 50)}</div>'
            f'<div class="meta">SMA200 {fmt(p200)}% {_breadth_sema(p200, 30, 60)}</div>'
            f'<div class="meta">Aggiornato: {format_iso_dt(pct_sma.get("fetched_at"))}</div>'
            f'{_origin_html(pct_sma)}</div>'
        )

    insider = data.get("insider", {})
    if insider.get("status") == "error":
        parts.append(_error_card("Insider (bonus)", insider))
    else:
        total_ins = insider.get("total", {})
        n_bonus = total_ins.get("tickers_with_bonus", 0)
        max_bonus = total_ins.get("max_bonus", 0.0)
        max_ticker = total_ins.get("max_ticker")
        max_html = f'<span class="ticker">{html_mod.escape(str(max_ticker))}</span>' if max_ticker else "—"
        parts.append(
            f'<div class="card"{_age_attrs(insider.get("fetched_at"), insider.get("stale_after_hours"))}><div class="label">Insider (bonus)</div>'
            f'<div class="value">{n_bonus} titoli</div>'
            f'<div class="meta">Max bonus {fmt(max_bonus)} ({max_html})</div>'
            f'<div class="meta">Aggiornato: {format_iso_dt(insider.get("fetched_at"))}</div></div>'
        )

    aaii = data.get("aaii", {})
    if aaii.get("status") == "error":
        parts.append(_error_card("AAII Sentiment", aaii))
    else:
        bullish = aaii.get("bullish")
        bearish = aaii.get("bearish")
        neutral = aaii.get("neutral")
        aaii_source = aaii.get("source")
        aaii_source_html = f' · Fonte: {html_mod.escape(str(aaii_source))}' if aaii_source else ""
        parts.append(
            f'<div class="card"{_age_attrs(aaii.get("fetched_at"), aaii.get("stale_after_hours"))}><div class="label">AAII Sentiment</div>'
            f'<div class="value">B {fmt(bullish)} · N {fmt(neutral)} · R {fmt(bearish)}</div>'
            f'<div class="meta">Aggiornato: {format_iso_dt(aaii.get("fetched_at"))}'
            f' (prossimo: {aaii.get("next_expected", "—")}){aaii_source_html}</div>'
            f'{_origin_html(aaii)}</div>'
        )

    naaim = data.get("naaim")
    if naaim is not None:
        if naaim.get("status") == "error":
            parts.append(_error_card("NAAIM Exposure", naaim))
        else:
            naaim_source = naaim.get("source")
            naaim_source_html = f' · Fonte: {html_mod.escape(str(naaim_source))}' if naaim_source else ""
            parts.append(
                f'<div class="card"{_age_attrs(naaim.get("fetched_at"), naaim.get("stale_after_hours"))}><div class="label">NAAIM Exposure</div>'
                f'<div class="value">{fmt(naaim.get("exposure"))}</div>'
                f'<div class="meta">Aggiornato: {format_iso_dt(naaim.get("fetched_at"))}{naaim_source_html}</div>'
                f'{_origin_html(naaim)}</div>'
            )

    return f'<div class="cards">{"".join(parts)}</div>'
