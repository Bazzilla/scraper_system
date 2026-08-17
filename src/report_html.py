"""Static HTML report generator.

Reads the consolidated output.json produced by the orchestrator and renders a
self-contained HTML page (dark theme with light toggle) showing market
indicators, per-sector ticker tables with technical indicators and semaphores,
and last-update timestamps.

Standalone script: ``render(config_path)`` — not wired into the orchestrator.

REMINDER: when a new scraper/module is added, update this module so the report
renders it too (see README "Report HTML statico").
"""

from __future__ import annotations

import html as html_mod
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

DEFAULT_HTML_PATH = "output/report.html"

_CSS = """\
:root { --bg: #0f1419; --card: #1a212b; --border: #2c3542; --text: #e6edf3;
        --muted: #8b949e; --green: #2ea043; --yellow: #d29922; --red: #f85149;
        --neutral: #58a6ff; }
[data-theme="light"] { --bg: #f6f8fa; --card: #ffffff; --border: #d0d7de;
        --text: #1f2328; --muted: #57606a; --green: #1a7f37; --yellow: #9a6700;
        --red: #cf222e; --neutral: #0969da; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        sans-serif; background: var(--bg); color: var(--text); line-height: 1.5;
        padding: 24px; }
.container { max-width: 1100px; margin: 0 auto; }
header { display: flex; justify-content: space-between; align-items: center;
        flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }
h1 { font-size: 1.5rem; }
.sub { color: var(--muted); font-size: 0.9rem; }
.badge { padding: 2px 10px; border-radius: 999px; font-size: 0.8rem;
        font-weight: 600; }
.badge.fresh { background: var(--green); color: #fff; }
.badge.stale { background: var(--red); color: #fff; }
button#theme-toggle { background: var(--card); color: var(--text);
        border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px;
        cursor: pointer; font-size: 0.9rem; }
h2 { margin: 28px 0 12px; font-size: 1.15rem; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 16px; }
.card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 16px; }
.card .label { color: var(--muted); font-size: 0.8rem; text-transform: uppercase;
        letter-spacing: 0.05em; }
.card .value { font-size: 1.6rem; font-weight: 700; margin: 4px 0; }
.card .meta { color: var(--muted); font-size: 0.8rem; }
.sema { display: inline-block; padding: 1px 8px; border-radius: 6px;
        font-size: 0.75rem; font-weight: 600; }
.sema.overbought { background: var(--red); color: #fff; }
.sema.oversold { background: var(--green); color: #fff; }
.sema.warning { background: var(--yellow); color: #1f2328; }
.sema.critical { background: var(--red); color: #fff; }
.sema.ok { background: var(--green); color: #fff; }
.sema.neutral { background: var(--card); border: 1px solid var(--border);
        color: var(--neutral); }
.sema.fear { background: var(--red); color: #fff; }
.sema.greed { background: var(--green); color: #fff; }
.sema.extreme_fear { background: var(--red); color: #fff; }
.sema.extreme_greed { background: var(--green); color: #fff; }
.sema-cell { display: flex; justify-content: space-between; align-items: center;
        gap: 8px; width: 100%; }
.sema-val { white-space: nowrap; }
table { width: 100%; border-collapse: collapse; background: var(--card);
        border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
th, td { padding: 8px 12px; text-align: right; border-bottom: 1px solid var(--border);
        font-size: 0.9rem; }
th { background: var(--card); color: var(--muted); font-weight: 600;
        text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.04em;
        text-align: center; }
td:first-child, th:first-child { text-align: left; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(88, 166, 255, 0.06); }
.ticker { font-weight: 700; }
.name { color: var(--muted); font-size: 0.8rem; }
footer { margin-top: 32px; color: var(--muted); font-size: 0.85rem;
        border-top: 1px solid var(--border); padding-top: 16px; }
.legend { margin-top: 24px; }
.legend-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
        gap: 12px; }
.legend-card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 12px 16px; }
.legend-card summary { cursor: pointer; font-weight: 600; font-size: 0.9rem;
        display: flex; justify-content: space-between; align-items: center;
        gap: 8px; list-style: none; }
.legend-card summary::-webkit-details-marker { display: none; }
.legend-card summary::after { content: "ℹ️"; font-size: 0.9rem; }
.legend-card[open] summary::after { content: "✖"; font-size: 0.9rem; }
.legend-card .legend-detail { margin-top: 8px; color: var(--text); font-size: 0.85rem;
        border-top: 1px solid var(--border); padding-top: 8px; }
.legend-card .legend-range { color: var(--muted); font-size: 0.8rem; }
.guide { margin-top: 24px; background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 16px; }
.guide h3 { font-size: 1rem; margin-bottom: 8px; }
.guide ul { padding-left: 20px; }
.guide li { margin: 6px 0; }
.sema-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
        margin-right: 6px; vertical-align: middle; }
.sema-dot.ok, .sema-dot.oversold { background: var(--green); }
.sema-dot.warning { background: var(--yellow); }
.sema-dot.critical, .sema-dot.overbought { background: var(--red); }
.sema-dot.neutral { background: var(--neutral); }
.signal { display: inline-block; padding: 2px 10px; border-radius: 6px;
        font-size: 0.78rem; font-weight: 700; white-space: nowrap; }
.signal.buy { background: var(--green); color: #fff; }
.signal.watchlist { background: var(--yellow); color: #1f2328; }
.signal.hold { background: var(--card); border: 1px solid var(--border);
        color: var(--neutral); }
.indicator-matrix { margin-top: 24px; }
.indicator-matrix table { width: 100%; }
.indicator-matrix td { text-align: left; vertical-align: top; }
.indicator-matrix th { text-align: left; }
"""

_SCRIPT = """\
<script>
(function () {
  var saved = localStorage.getItem("report-theme");
  var theme = saved || "dark";
  document.documentElement.setAttribute("data-theme", theme);
  var btn = document.getElementById("theme-toggle");
  btn.textContent = theme === "dark" ? "☀️ Light" : "🌙 Dark";
  btn.addEventListener("click", function () {
    var next = theme === "dark" ? "light" : "dark";
    theme = next;
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("report-theme", next);
    btn.textContent = next === "dark" ? "☀️ Light" : "🌙 Dark";
  });
})();
</script>
"""

_FGI_ZONES = [
    (25, "extreme_fear"),
    (45, "fear"),
    (56, "neutral"),
    (75, "greed"),
    (101, "extreme_greed"),
]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def semaphore_class(value: float | None, metric: str) -> str:
    """Return the CSS class for a metric's semaphore."""
    if value is None:
        return "neutral"
    if metric == "rsi":
        if value > 70:
            return "overbought"
        if value < 30:
            return "oversold"
        return "neutral"
    if metric == "mfi":
        if value > 80:
            return "overbought"
        if value < 20:
            return "oversold"
        return "neutral"
    if metric == "drawdown":
        if value >= -5:
            return "ok"
        if value >= -15:
            return "warning"
        return "critical"
    return "neutral"


def market_regime(fgi_score: float | None) -> str:
    """Classify the market regime from the Fear & Greed score.

    Returns 'greed', 'fear' or 'neutral'. Missing score → 'neutral' (no gate).
    Boundaries follow the strategy (F1): Greed starts at 56, Fear up to 45.
    """
    if fgi_score is None:
        return "neutral"
    if fgi_score >= 56:
        return "greed"
    if fgi_score <= 45:
        return "fear"
    return "neutral"


def compute_signal(
    entry: dict[str, Any],
    regime: str = "neutral",
    proxy_accepted: set[str] | frozenset[str] | None = None,
) -> str:
    """Compute a trading signal from a ticker's indicators and market regime.

    Follows the project's trading strategy (buy-the-dip): technical weakness
    (price below SMAs, deep drawdown) is the SCREENING INPUT for a potential
    entry, not a sell reason. A sell is only justified by an explicit exit
    trigger (take-profit, fundamental deterioration, time-stop — Regola 4),
    which the dashboard cannot compute from price data alone.

    Scoring (per indicator, +1 bullish / -1 bearish):
    - RSI < 30 (oversold) → +1 ; RSI > 70 (overbought) → -1
    - MFI < 20 (oversold) → +1 ; MFI > 80 (overbought) → -1
    - price above SMA50 → +1 ; below → -1
    - price above SMA200 → +1 ; below → -1
    - drawdown >= -5 (near high) → +1 ; < -15 (critical) → -1

    Classes:
    - 'buy'       (score >= +2): convergence of oversold + strength
    - 'watchlist' (score <= -2): deep weakness — the buy-the-dip profile, but
                   NOT a sell reason. Watch, do not enter without confirmations.
    - 'hold'      otherwise: mixed signals / no opportunity.

    Market gate (Regola 0): in GREED no 'buy' (do not chase a hot market); in
    FEAR deep weakness stays 'watchlist' (discounts are more real). The gate
    never produces a sell.

    Proxy guard (audit 2026-08-14): this scorer consumes only IMPLEMENTED
    per-ticker indicators (rsi_14, mfi_14, sma_50, sma_200, drawdown_52w from
    the OHLCV cache). Proxy indicators (VIX spot, sector breadth) are NOT
    passed here and must never be treated as the original strategy indicator.
    If a caller wants a proxy to influence scoring, it must do so explicitly
    via ``proxy_accepted`` and the strategy indicator registry; the market
    regime gate uses the FGI (implemented), never a proxy FGI variant.
    """
    accepted = set(proxy_accepted or ())
    score = 0

    rsi = entry.get("rsi_14")
    if rsi is not None:
        if rsi < 30:
            score += 1
        elif rsi > 70:
            score -= 1

    mfi = entry.get("mfi_14")
    if mfi is not None:
        if mfi < 20:
            score += 1
        elif mfi > 80:
            score -= 1

    price = entry.get("last_close")
    sma50 = entry.get("sma_50")
    if price is not None and sma50 is not None:
        score += 1 if price >= sma50 else -1

    sma200 = entry.get("sma_200")
    if price is not None and sma200 is not None:
        score += 1 if price >= sma200 else -1

    drawdown = entry.get("drawdown_52w")
    if drawdown is not None:
        if drawdown >= -5:
            score += 1
        elif drawdown < -15:
            score -= 1

    if score >= 2:
        signal = "buy"
    elif score <= -2:
        signal = "watchlist"
    else:
        signal = "hold"

    # Market gate (Regola 0): climate must point in the same direction.
    if regime == "greed" and signal == "buy":
        return "hold"
    return signal


def _signal_badge(signal: str) -> str:
    """Render the signal badge for a ticker."""
    cls = {"buy": "buy", "watchlist": "watchlist", "hold": "hold"}[signal]
    label = {"buy": "COMPRA", "watchlist": "WATCHLIST", "hold": "ATTENDI"}[signal]
    icon = {"buy": "🟢", "watchlist": "🟠", "hold": "⚪"}[signal]
    return f'<span class="signal {cls}">{icon} {label}</span>'


_ITALIAN_MONTHS = [
    "gen", "feb", "mar", "apr", "mag", "giu",
    "lug", "ago", "set", "ott", "nov", "dic",
]


def format_iso_dt(iso: str | None) -> str:
    """Format an ISO timestamp into a readable Italian datetime string."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        month = _ITALIAN_MONTHS[dt.month - 1]
        return f"{dt.day:02d} {month} {dt.year}, {dt.hour:02d}:{dt.minute:02d}"
    except ValueError:
        return iso


def fmt(value: float | None) -> str:
    """Format a number, or return an em-dash for None."""
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def _badge(status: str) -> str:
    cls = "fresh" if status == "fresh" else "stale"
    return f'<span class="badge {cls}">{html_mod.escape(status)}</span>'


def _age_attrs(fetched_at: str | None, stale_after_hours: float | None) -> str:
    """Return HTML data-* attributes for client-side age computation.

    Returns a string like `` data-fetched-at="..." data-stale-hours="..."``
    (leading space included) or an empty string when the timestamp or the
    validity window is missing.
    """
    if not fetched_at or stale_after_hours is None:
        return ""
    iso = html_mod.escape(fetched_at)
    return f' data-fetched-at="{iso}" data-stale-hours="{stale_after_hours}"'


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
        parts.append(
            f'<div class="card"{_age_attrs(fgi.get("fetched_at"), fgi.get("stale_after_hours"))}><div class="label">CNN Fear &amp; Greed</div>'
            f'<div class="value">{fmt(fgi_score)}</div>{zone_badge}'
            f'<div class="meta">Aggiornato: {format_iso_dt(fgi.get("fetched_at"))}{source_html}</div>'
            f'{_origin_html(fgi)}</div>'
        )

    vix = data.get("vix", {})
    if vix.get("status") == "error":
        parts.append(_error_card("VIX Spot", vix))
    else:
        vix_ts = data.get("vix_term_structure", {})
        if vix_ts.get("status") == "fresh":
            ts_note = (
                f' · M1 {fmt(vix_ts.get("m1"))} · M2 {fmt(vix_ts.get("m2"))}'
                f' · {html_mod.escape(str(vix_ts.get("structure", "")))}'
                f' ({fmt(vix_ts.get("contango_pct_1_2"))}%)'
            )
        else:
            ts_note = " · term structure non disponibile"
        parts.append(
            f'<div class="card"{_age_attrs(vix.get("fetched_at"), vix.get("stale_after_hours"))}><div class="label">VIX Spot '
            '<span class="sema warning">proxy</span></div>'
            f'<div class="value">{fmt(vix.get("vix_close"))}</div>'
            f'<div class="meta">Aggiornato: {format_iso_dt(vix.get("fetched_at"))}{ts_note}</div>'
            f'{_origin_html(vix_ts)}</div>'
        )

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
        parts.append(_error_card("Breadth settoriale", pct_sma))
    else:
        total_stats = pct_sma.get("total", {})
        p50 = total_stats.get("pct_sma50")
        p200 = total_stats.get("pct_sma200")

        def _breadth_sema(pct: float | None, threshold_low: float, threshold_mid: float) -> str:
            if pct is None:
                return ""
            cls = "fear" if pct < threshold_low else (
                "warning" if pct < threshold_mid else "ok")
            return f'<span class="sema {cls}">{cls}</span>'

        parts.append(
            f'<div class="card"{_age_attrs(pct_sma.get("fetched_at"), pct_sma.get("stale_after_hours"))}><div class="label">Breadth settoriale '
            '<span class="sema warning">proxy</span></div>'
            f'<div class="value">SMA50 {fmt(p50)}% {_breadth_sema(p50, 20, 50)}</div>'
            f'<div class="meta">SMA200 {fmt(p200)}% {_breadth_sema(p200, 30, 60)}</div>'
            f'<div class="meta">Aggiornato: {format_iso_dt(pct_sma.get("fetched_at"))}</div></div>'
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


def _sema(value: float | None, metric: str) -> str:
    cls = semaphore_class(value, metric)
    badge = "" if cls in ("", "neutral") else f'<span class="sema {cls}">{cls}</span>'
    if badge:
        # Layout flessibile: valore a sinistra, badge a destra (ben separati).
        return (
            f'<span class="sema-cell">'
            f'<span class="sema-val">{fmt(value)}</span>{badge}'
            f"</span>"
        )
    return f'<span class="sema-val">{fmt(value)}</span>'


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
            "<tr>"
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


def _status_badge(status: str) -> str:
    """Render a strategy-coverage status badge.

    Handles implementation_status values (implemented/proxy/missing/
    manual_supported) and runtime source values (scraped/manual/missing).
    """
    if status in ("implemented", "scraped"):
        cls, label = "sema ok", status
    elif status in ("proxy", "manual", "manual_supported"):
        cls, label = "sema warning", status
    else:
        cls, label = "sema critical", status
    return f'<span class="sema {cls}">{html_mod.escape(label)}</span>'


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


_LEGEND_MARKET = [
    {
        "name": "Fear &amp; Greed (FGI)",
        "range": "0-100",
        "short": "Sentiment del mercato: meno di 25 = paura estrema, oltre 75 = avidità estrema.",
        "detail": (
            "Indice composito CNN che misura il sentiment prevalente degli investitori. "
            "Valori bassi (paura) spesso coincidono con fasi di debolezza o con punti di "
            "massima cautela; valori alti (avidità) indicano ottimismo spinto, che può "
            "precedere correzioni. Va letto come termometro dell'umore di mercato, non "
            "come segnale di compra/vendita diretto."
        ),
    },
    {
        "name": "VIX",
        "range": "indice",
        "short": "Volatilità implicita: oltre 30 tensione elevata, sotto 15 mercato calmo.",
        "detail": (
            "Detto anche 'indice della paura', stima la volatilità attesa del mercato "
            "azionario USA a 30 giorni. Un VIX alto segnala incertezza e possibili "
            "oscillazioni forti; un VIX basso indica condizioni tranquille. Non va usato "
            "da solo per decidere, ma come indicatore del clima di rischio complessivo. "
            "<strong>Nota (audit 2026-08-14)</strong>: la strategia F3/10 richiede la "
            "<em>VIX term structure</em> (backwardation M1&gt;M2 = panico a breve); questa "
            "card mostra il <em>VIX spot</em> (livello), che è un indicatore diverso. "
            "La term structure non è scrapabile da fonti gratuite (VIX Central/VolChart "
            "bloccato), ma può essere inserita manualmente (M1/M2) via "
            "<code>manual_overrides.yaml</code> — valori leggibili da "
            "https://vixcentral.com/. Il dato spot resta un proxy parziale."
        ),
    },
    {
        "name": "AAII Sentiment",
        "range": "%",
        "short": "Percentuale di investitori retail bullish, neutral e bearish.",
        "detail": (
            "Sondaggio settimanale AAII sull'orientamento degli investitori privati. "
            "Un'estrema prevalenza di bullish può segnalare euforia (possibile eccesso), "
            "un'estrema prevalenza di bearish può segnalare pessimismo diffuso. Indicatore "
            "contrarian: spesso i massimi si formano con sentiment molto positivo e i "
            "minimi con sentiment molto negativo."
        ),
    },
    {
        "name": "Put/Call Ratio (PCR)",
        "range": "ratio",
        "short": "Put venduti vs call: oltre 0.80 = paura, sotto 0.70 = avidità.",
        "detail": (
            "Rapporto tra il volume di opzioni put e call (equity). Un PCR alto "
            "(> 0.80) indica che gli investitori comprano più protezione che "
            "speculazione — segnale di paura, storicamente favorevole per chi "
            "cerca sconti (buy-the-dip). Un PCR basso (< 0.70) indica ottimismo. "
            "Fonte: CBOE (lag 1 giorno di trading)."
        ),
    },
    {
        "name": "Breadth settoriale (% sopra SMA)",
        "range": "%",
        "short": "Quota di ticker dei settori sopra SMA50/SMA200.",
        "detail": (
            "Percentuale di ticker (semiconduttori+difesa) con prezzo sopra la media "
            "mobile a 50 e 200 giorni. Sotto il 20% su SMA50 il settore è ipervenduto "
            "diffuso (potenziale opportunità); sotto il 30% su SMA200 il mercato è "
            "deteriorato. Sopra il 50%/60% la struttura è positiva. Calcolata "
            "localmente dai dati OHLCV (IndexIndicators non è scrapabile). "
            "<strong>Nota (audit 2026-08-14)</strong>: la strategia F3/13-14 usa le "
            "soglie &lt;20% / &lt;30% riferite a <em>tutto il mercato USA</em>; questa "
            "card calcola la breadth <em>solo sui 29 ticker monitorati</em> (2 settori). "
            "È un proxy settoriale, non l'indicatore di mercato originale."
        ),
    },
    {
        "name": "Insider (bonus opportunità)",
        "range": "punti",
        "short": "Acquisti insider dei dirigenti come bonus alla matrice Opportunità.",
        "detail": (
            "Bonus H5 della strategia: <strong>+0.5</strong> se almeno 2 acquisti "
            "insider (dirigenti) sul mercato aperto negli ultimi 30 giorni con valore "
            "complessivo oltre $100K; <strong>+1.0</strong> se CEO o CFO compra; "
            "cumulabile fino a <strong>max +1.5</strong>. Gli acquisti insider sono tra "
            "i segnali più forti perché chi conosce l'azienda mette soldi veri sul "
            "titolo. Fonte: OpenInsider (Form 4 SEC, lag 2 giorni)."
        ),
    },
]

_LEGEND_STOCK = [
    {
        "name": "RSI",
        "range": "0-100",
        "short": "Momentum: oltre 70 ipercomprato, sotto 30 ipervenduto.",
        "detail": (
            "Relative Strength Index: misura la forza del movimento dei prezzi. "
            "RSI oltre 70 indica un titolo potenzialmente ipercomprato (il prezzo è "
            "salito troppo in fretta, possibile correzione); sotto 30 ipervenduto "
            "(possibile rimbalzo). Se molti titoli di un settore hanno RSI alto, il "
            "settore nel suo insieme appare 'caldo'."
        ),
    },
    {
        "name": "MFI",
        "range": "0-100",
        "short": "Flusso monetario: oltre 80 ipercomprato, sotto 20 ipervenduto.",
        "detail": (
            "Money Flow Index: come l'RSI ma ponderato per il volume. Misura la "
            "pressione di acquisto/vendita. Valori estremi indicano eccessi che spesso "
            "precedono inversioni. Un MFI in salita con prezzi in salita conferma il "
            "trend; divergenze (prezzi che salgono, MFI che scende) segnalano debolezza."
        ),
    },
    {
        "name": "OBV",
        "range": "cumulativo",
        "short": "Conferma del trend attraverso il volume.",
        "detail": (
            "On-Balance Volume: accumula il volume in base alla direzione del prezzo "
            "(giorni in rialzo sommano, giorni in ribasso sottraggono). Un OBV in "
            "tendenza con i prezzi conferma il movimento; un OBV che diverge dai prezzi "
            "può anticipare un'inversione. Utile come conferma, non come segnale isolato."
        ),
    },
    {
        "name": "SMA50 / SMA200",
        "range": "prezzo",
        "short": "Media mobile: trend di medio (50) e lungo (200) termine.",
        "detail": (
            "Simple Moving Average: prezzo medio degli ultimi N giorni. Il prezzo sopra "
            "la SMA50 indica trend di medio termine positivo, sopra la SMA200 trend di "
            "lungo termine positivo. L'incrocio prezzo/SMA o SMA50/SMA200 è usato come "
            "segnale di cambio trend (golden cross / death cross)."
        ),
    },
    {
        "name": "Drawdown",
        "range": "%",
        "short": "Distanza dal massimo delle 52 settimane: ok, attenzione, critico.",
        "detail": (
            "Indica di quanto il prezzo è sceso rispetto al massimo dell'ultimo anno. "
            "Un drawdown lieve (fino a -5%) è fisiologico; tra -5% e -15% la correzione "
            "è più marcata; oltre -15% la situazione è critica. Valuta la debolezza "
            "relativa del titolo rispetto al suo stesso recente massimo."
        ),
    },
    {
        "name": "Segnale",
        "range": "COMPRA / WATCHLIST / ATTENDI",
        "short": "Sintesi degli indicatori del ticker + clima di mercato.",
        "detail": (
            "Punteggio che combina RSI, MFI, SMA50, SMA200 e drawdown (+1 bullish, "
            "-1 bearish per indicatore). <strong>COMPRA</strong> (punteggio ≥ +2): "
            "convergenza di segnali di ipervenduto e forza — possibile ingresso. "
            "<strong>WATCHLIST</strong> (punteggio ≤ -2): debolezza profonda — è il "
            "profilo buy-the-dip (calo ≥10%), ma NON è un motivo di vendita: osserva, "
            "non entrare senza conferme (causa del calo, MFI, volume). <strong>ATTENDI</strong> "
            "(tra -1 e +1): segnali misti, meglio aspettare.<br>"
            "<strong>Gate di mercato (FGI)</strong>: il clima deve puntare nella stessa "
            "direzione del titolo. In zona <em>greed</em> (FGI ≥ 55) nessun COMPRA — non "
            "si insegue un mercato caldo. <strong>Nessun VENDI viene emesso dai dati "
            "tecnici</strong>: vendere richiede un trigger di uscita esplicito (take-profit "
            "+15/20%, deterioramento fondamentale, time-stop 18 mesi) che il dashboard "
            "non può calcolare. Non è un consiglio finanziario."
        ),
    },
]

_LEGEND_SEMAPHORES = [
    {
        "name": "Semafori",
        "range": "",
        "short": "Colori che riassumono lo stato di ogni indicatore.",
        "detail": (
            "<span class='sema-dot ok'></span><strong>Verde (ok / oversold)</strong>: "
            "condizione favorevole o di ipervenduto (potenziale rimbalzo).<br>"
            "<span class='sema-dot warning'></span><strong>Giallo (warning)</strong>: "
            "zona di cautela, correzione marcata.<br>"
            "<span class='sema-dot critical'></span><strong>Rosso (critical / overbought)</strong>: "
            "condizione critica o di ipercomprato (possibile correzione).<br>"
            "<span class='sema-dot neutral'></span><strong>Blu (neutral)</strong>: "
            "valore in zona neutra, nessun segnale particolare.<br>"
            "<strong>Nelle card di mercato</strong> (FGI, Put/Call Ratio) il colore segue "
            "il <em>sentiment</em>: verde = greed/avidità (ottimismo), rosso = "
            "fear/paura (cautela). Non va confuso con ok/critical dei singoli ticker."
        ),
    },
]

_GUIDE = (
    "<div class='guide'>"
    "<h3>Guida operativa — quando comprare o vendere</h3>"
    "<p>La tabella non è un consiglio finanziario: è un riepilogo tecnico. I segnali "
    "vanno valutati insieme, non singolarmente. Ecco una lettura indicativa:</p>"
    "<ul>"
    "<li><strong>Possibile acquisto</strong> se più indicatori convergono su condizioni "
    "di debolezza con segnali di inversione: RSI/MFI ipervenduti (sotto 30/20), drawdown "
    "ampio ma in miglioramento, prezzo che torna sopra la SMA50, sentiment di mercato in "
    "zona paura (FGI basso). La convergenza di più segnali riduce il rischio di un falso "
    "minimo.</li>"
    "<li><strong>Possibile vendita (se detenuto in profitto)</strong> se il titolo mostra "
    "segnali di eccesso o indebolimento: RSI/MFI ipercomprati (sopra 70/80), drawdown in "
    "peggioramento, prezzo che perde la SMA50 o la SMA200, sentiment di mercato in zona "
    "avidità (FGI alto). L'idea è proteggere il guadagno quando la probabilità di "
    "correzione aumenta.</li>"
    "<li><strong>Cautela / nessuna azione</strong> se i segnali sono misti: alcuni "
    "indicatori positivi e altri negativi. In quel caso è meglio attendere conferme "
    "piuttosto che agire su un segnale singolo.</li>"
    "<li>Gli indicatori di mercato (FGI, VIX, AAII) descrivono il <em>clima generale</em>; "
    "gli indicatori del ticker (RSI, MFI, OBV, SMA, drawdown) descrivono il <em>titolo "
    "singolo</em>. I segnali più forti arrivano quando clima e titolo puntano nella stessa "
    "direzione.</li>"
    "</ul>"
    "<p><em>Disclaimer: strumento informativo a scopo didattico. Non costituisce "
    "consulenza finanziaria.</em></p>"
    "</div>"
)


def _legend_item(item: dict[str, str]) -> str:
    """Render one expandable legend item using native <details>/<summary>."""
    return (
        "<details class='legend-card'>"
        f"<summary>{item['name']} <span class='legend-range'>({item['range']})</span></summary>"
        f"<div class='legend-detail'><p>{item['short']}</p>"
        f"<p>{item['detail']}</p></div>"
        "</details>"
    )


def render_legend() -> str:
    """Render the indicators legend with per-row toggles and the guide."""
    market = "".join(_legend_item(item) for item in _LEGEND_MARKET)
    stock = "".join(_legend_item(item) for item in _LEGEND_STOCK)
    sema = "".join(_legend_item(item) for item in _LEGEND_SEMAPHORES)
    return (
        "<div class='legend'>"
        "<h2>Legenda indicatori</h2>"
        "<div class='legend-grid'>"
        f"<div><h3>Indicatori di mercato</h3>{market}</div>"
        f"<div><h3>Indicatori azionari</h3>{stock}</div>"
        "</div>"
        f"<h3>Semafori</h3>{sema}"
        f"{_GUIDE}"
        "</div>"
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


def build_page(data: dict[str, Any]) -> str:
    """Assemble the complete HTML document."""
    stale = data.get("stale_summary", {})
    overall = "fresh" if stale.get("stale", 0) == 0 else "stale"
    title = "Market Dashboard"
    html_doc = (
        "<!DOCTYPE html>\n<html lang=\"it\" data-theme=\"dark\">\n<head>"
        "<meta charset=\"utf-8\">"
        f"<title>{title}</title>"
        f"<style>{_CSS}</style>"
        "</head>\n<body><div class=\"container\">"
        "<header>"
        f"<div><h1>📊 {title}</h1>"
        f'<div class="sub">Generato: {format_iso_dt(data.get("generated_at"))}</div></div>'
        f'<div><span class="badge {overall}">{overall}</span> '
        '<button id="theme-toggle" type="button">☀️ Light</button></div>'
        "</header>"
        f"<h2>Indicatori di mercato</h2>"
        f"{render_market_cards(data)}"
        f"{render_indicator_matrix(data.get('strategy_indicators', {}))}"
        f"{_ticker_sections(data)}"
        f"{render_stale_summary(stale)}"
        f"{render_legend()}"
        "</div>"
        f"{_SCRIPT}"
        "</body>\n</html>"
    )
    return html_doc


def render(config_path: str, output_path: str | None = None) -> str:
    """Render the HTML report from the consolidated output.json.

    Args:
        config_path: Path to config.yaml (used to resolve output.json_path).
        output_path: Where to write the HTML. Defaults to ``output/report.html``
            relative to the config file's directory.

    Returns:
        The path of the generated HTML file.

    Raises:
        FileNotFoundError: If the output JSON does not exist.
    """
    with open(config_path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    base_dir = Path(config_path).resolve().parent
    output_cfg = config.get("output", {})
    json_path = base_dir / output_cfg.get("json_path", "output/output.json")

    if not json_path.exists():
        raise FileNotFoundError(
            f"Output JSON not found at {json_path}. Run the orchestrator first."
        )

    with json_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    html_path = output_path or str(base_dir / DEFAULT_HTML_PATH)
    path = Path(html_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_page(data), encoding="utf-8")
    return str(path)
