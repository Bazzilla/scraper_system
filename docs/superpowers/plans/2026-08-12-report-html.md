# Report HTML Statistico Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Creare `src/report_html.py` che legge `output/output.json` e genera una pagina HTML statica (dark theme con toggle light) con card per indicatori di mercato, tabelle per categoria con semafori, e date di aggiornamento.

**Architecture:** Script standalone, funzioni pure per la costruzione delle sezioni HTML. `render(config_path, output_path=None)` risolve il path di output.json dal config, genera la pagina self-contained (CSS inline + toggle JS), la scrive su disco. Nessuna dipendenza esterna.

**Tech Stack:** Python 3.14 (venv .venv), stdlib (json, datetime, html, pathlib)

## Global Constraints

- **Venv obbligatorio**: usare `../.venv/bin/python` (da src/).
- Script **standalone** — NON agganciare all'orchestratore (decisione utente).
- **Funzioni pure** per la costruzione HTML, testabili senza rete.
- **CSS inline** nel template — pagina self-contained, nessuna dipendenza esterna.
- **Toggle dark/light** con JS inline + localStorage; default dark.
- **Semafori**: valori numerici SEMPRE visibili + badge/classe colore.
- Type hints su tutte le funzioni, snake_case, errori descrittivi.
- Formato output.json: chiavi `generated_at`, `fgi` (score, zone, fetched_at), `aaii` (bullish, bearish, neutral, fetched_at), `vix` (vix_close, fetched_at), `ohlcv` (per categoria → ticker → {symbol, name, last_close, last_date, fetched_at, status}), `indicators` (per categoria → ticker → {rsi_14, obv, mfi_14, sma_50, sma_200, drawdown_52w, symbol, name, fetched_at, status}), `stale_summary` (total_sources, fresh, stale, stale_details, signal_reliability).
- **Il progetto NON è un repo git** → i passi "Commit" vanno saltati.
- Test suite: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`.

---

### Task 1: `report_html.py` — funzioni pure + render()

**Files:**
- Create: `src/report_html.py`
- Create: `src/tests/test_report_html.py`

**Interfaces:**
- Consumes: `output/output.json` (formato file.json), `config.yaml` (sezione output.json_path)
- Produces:
  - `semaphore_class(value: float | None, metric: str) -> str` — "overbought"/"oversold"/"warning"/"critical"/"neutral"/""
  - `format_iso_dt(iso: str) -> str` — "2026-08-12T14:30:07+00:00" → "12 ago 2026, 14:30"
  - `fmt(value: float | None) -> str` — formatta numero o "—"
  - `render_market_cards(data: dict) -> str` — card FGI/VIX/AAII
  - `render_ticker_table(category: str, entries: dict) -> str` — tabella con semafori
  - `render_stale_summary(summary: dict) -> str`
  - `build_page(data: dict) -> str` — documento HTML completo
  - `render(config_path: str, output_path: str | None = None) -> str` — entry point CLI

- [ ] **Step 1: Scrivi i test falliti in `src/tests/test_report_html.py`**

```python
"""Unit tests for the static HTML report generator (pure functions)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from report_html import (
    build_page,
    fmt,
    format_iso_dt,
    render,
    render_market_cards,
    render_ticker_table,
    semaphore_class,
)


def _sample_data() -> dict:
    return {
        "generated_at": "2026-08-12T14:30:07+00:00",
        "fgi": {"score": 62.65, "zone": "greed", "fetched_at": "2026-08-12T14:29:42+00:00",
                "frequency": "daily", "stale_after_hours": 24, "status": "fresh"},
        "aaii": {"bullish": 37.0, "bearish": 38.0, "neutral": 25.0,
                 "fetched_at": "2026-08-12T14:29:43+00:00",
                 "frequency": "weekly", "stale_after_hours": 168, "status": "fresh",
                 "next_expected": "2026-08-13"},
        "vix": {"vix_close": 15.28, "fetched_at": "2026-08-12T14:29:44+00:00",
                "frequency": "daily", "stale_after_hours": 24, "status": "fresh"},
        "ohlcv": {
            "semiconductors": {
                "AMAT": {"symbol": "AMAT", "name": "Applied Materials",
                         "last_close": 548.87, "last_date": "2026-08-12",
                         "fetched_at": "2026-08-12T14:30:06+00:00",
                         "frequency": "daily", "stale_after_hours": 24, "status": "fresh"}
            }
        },
        "indicators": {
            "semiconductors": {
                "AMAT": {"rsi_14": 52.08, "obv": 356286653.0, "mfi_14": 34.97,
                         "sma_50": 557.88, "sma_200": 385.3, "drawdown_52w": -24.08,
                         "symbol": "AMAT", "name": "Applied Materials",
                         "fetched_at": "2026-08-12T14:30:06+00:00",
                         "frequency": "daily", "stale_after_hours": 24, "status": "fresh"}
            }
        },
        "stale_summary": {"total_sources": 5, "fresh": 5, "stale": 0,
                          "stale_details": [], "signal_reliability": "high"},
    }


class TestSemaphoreClass(unittest.TestCase):
    def test_rsi_overbought(self):
        self.assertEqual(semaphore_class(75.0, "rsi"), "overbought")

    def test_rsi_oversold(self):
        self.assertEqual(semaphore_class(25.0, "rsi"), "oversold")

    def test_rsi_neutral(self):
        self.assertEqual(semaphore_class(50.0, "rsi"), "neutral")

    def test_mfi_overbought(self):
        self.assertEqual(semaphore_class(85.0, "mfi"), "overbought")

    def test_drawdown_critical(self):
        self.assertEqual(semaphore_class(-20.0, "drawdown"), "critical")

    def test_drawdown_warning(self):
        self.assertEqual(semaphore_class(-10.0, "drawdown"), "warning")

    def test_drawdown_ok(self):
        self.assertEqual(semaphore_class(-2.0, "drawdown"), "ok")

    def test_none_is_neutral(self):
        self.assertEqual(semaphore_class(None, "rsi"), "neutral")


class TestFormat(unittest.TestCase):
    def test_format_iso_dt(self):
        self.assertEqual(format_iso_dt("2026-08-12T14:30:07+00:00"), "12 ago 2026, 14:30")

    def test_fmt_number(self):
        self.assertEqual(fmt(548.87), "548.87")

    def test_fmt_none(self):
        self.assertEqual(fmt(None), "—")


class TestRenderSections(unittest.TestCase):
    def test_market_cards_contains_values(self):
        html = render_market_cards(_sample_data())
        self.assertIn("Fear &amp; Greed", html)
        self.assertIn("62.65", html)
        self.assertIn("15.28", html)
        self.assertIn("37.0", html)

    def test_ticker_table_contains_rows(self):
        data = _sample_data()
        html = render_ticker_table("semiconductors", data["indicators"]["semiconductors"])
        self.assertIn("AMAT", html)
        self.assertIn("52.08", html)
        self.assertIn("overbought", html)  # classe semaforo presente nel markup

    def test_build_page_contains_all_sections(self):
        html = build_page(_sample_data())
        self.assertIn("Market Dashboard", html)
        self.assertIn("SEMICONDUTTORI", html)
        self.assertIn("stale_summary", html)
        self.assertIn("dark", html)  # classe tema presente
        self.assertIn("localStorage", html)  # toggle JS presente


class TestRender(unittest.TestCase):
    def test_render_writes_html_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/config.yaml"
            data_path = f"{tmp}/output.json"
            with open(config_path, "w", encoding="utf-8") as fh:
                fh.write(
                    "output:\n"
                    f"  json_path: {data_path}\n"
                    "  db_path: output/audit.db\n"
                    "scrapers:\n"
                    "  fgi:\n"
                    "    module: scrapers.fgi_scraper\n"
                    "    output_key: fgi\n"
                    "    schedule: daily\n"
                )
            with open(data_path, "w", encoding="utf-8") as fh:
                json.dump(_sample_data(), fh)
            html_path = render(config_path, output_path=f"{tmp}/report.html")
            self.assertTrue(Path(html_path).exists())
            content = Path(html_path).read_text(encoding="utf-8")
            self.assertIn("Market Dashboard", content)

    def test_render_missing_output_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/config.yaml"
            with open(config_path, "w", encoding="utf-8") as fh:
                fh.write(
                    "output:\n"
                    f"  json_path: {tmp}/nonexistent.json\n"
                    "  db_path: output/audit.db\n"
                    "scrapers:\n"
                    "  fgi:\n"
                    "    module: scrapers.fgi_scraper\n"
                    "    output_key: fgi\n"
                    "    schedule: daily\n"
                )
            with self.assertRaises(FileNotFoundError):
                render(config_path)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Esegui i test per verificare che falliscano**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_report_html -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'report_html'`

- [ ] **Step 3: Implementa `src/report_html.py`**

```python
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
table { width: 100%; border-collapse: collapse; background: var(--card);
        border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
th, td { padding: 8px 12px; text-align: right; border-bottom: 1px solid var(--border);
        font-size: 0.9rem; }
th { background: var(--card); color: var(--muted); font-weight: 600;
        text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.04em; }
td:first-child, th:first-child { text-align: left; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(88, 166, 255, 0.06); }
.ticker { font-weight: 700; }
.name { color: var(--muted); font-size: 0.8rem; }
footer { margin-top: 32px; color: var(--muted); font-size: 0.85rem;
        border-top: 1px solid var(--border); padding-top: 16px; }
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
    (55, "neutral"),
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


def format_iso_dt(iso: str | None) -> str:
    """Format an ISO timestamp into a readable local datetime string."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d %b %Y, %H:%M")
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


def render_market_cards(data: dict[str, Any]) -> str:
    """Render the market indicator cards (FGI, VIX, AAII)."""
    parts: list[str] = []

    fgi = data.get("fgi", {})
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
    parts.append(
        '<div class="card"><div class="label">CNN Fear &amp; Greed</div>'
        f'<div class="value">{fmt(fgi_score)}</div>{zone_badge}'
        f'<div class="meta">Aggiornato: {format_iso_dt(fgi.get("fetched_at"))}</div></div>'
    )

    vix = data.get("vix", {})
    parts.append(
        '<div class="card"><div class="label">VIX Spot</div>'
        f'<div class="value">{fmt(vix.get("vix_close"))}</div>'
        f'<div class="meta">Aggiornato: {format_iso_dt(vix.get("fetched_at"))}</div></div>'
    )

    aaii = data.get("aaii", {})
    bullish = aaii.get("bullish")
    bearish = aaii.get("bearish")
    neutral = aaii.get("neutral")
    parts.append(
        '<div class="card"><div class="label">AAII Sentiment</div>'
        f'<div class="value">B {fmt(bullish)} · N {fmt(neutral)} · R {fmt(bearish)}</div>'
        f'<div class="meta">Aggiornato: {format_iso_dt(aaii.get("fetched_at"))}'
        f' (prossimo: {aaii.get("next_expected", "—")})</div></div>'
    )

    return f'<div class="cards">{"".join(parts)}</div>'


def _sema(value: float | None, metric: str) -> str:
    cls = semaphore_class(value, metric)
    badge = "" if cls in ("", "neutral") else f'<span class="sema {cls}">{cls}</span>'
    return f'{fmt(value)} {badge}'


def render_ticker_table(category: str, entries: dict[str, Any]) -> str:
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
            f'<td>{format_iso_dt(ind.get("fetched_at"))}</td>'
            "</tr>"
        )
    header = (
        "<thead><tr>"
        "<th>Ticker</th><th>Close</th><th>RSI</th><th>MFI</th><th>OBV</th>"
        "<th>SMA50</th><th>SMA200</th><th>Drawdown</th><th>Aggiornato</th>"
        "</tr></thead>"
    )
    return f"<table>{header}<tbody>{''.join(rows)}</tbody></table>"


def render_stale_summary(summary: dict[str, Any]) -> str:
    """Render the stale summary footer."""
    details = summary.get("stale_details", [])
    details_html = ""
    if details:
        items = "".join(f"<li>{html_mod.escape(str(d))}</li>" for d in details)
        details_html = f"<ul>{items}</ul>"
    return (
        "<footer>"
        f"<strong>Stato sorgenti:</strong> "
        f"{summary.get('fresh', 0)}/{summary.get('total_sources', 0)} fresh · "
        f"{summary.get('stale', 0)} stale · "
        f"affidabilità: {summary.get('signal_reliability', '—')}"
        f"{details_html}"
        "</footer>"
    )


def _ticker_sections(data: dict[str, Any]) -> str:
    """Render per-category ticker tables (from indicators; falls back to ohlcv)."""
    indicators = data.get("indicators", {})
    ohlcv = data.get("ohlcv", {})
    source = indicators if indicators else ohlcv
    if not source:
        return ""
    sections: list[str] = []
    for category in sorted(source):
        entries = source[category]
        if not isinstance(entries, dict) or "status" in entries and len(entries) <= 1:
            continue
        display = category.upper()
        sections.append(f"<h2>{html_mod.escape(display)} ({len(entries)})</h2>")
        sections.append(render_ticker_table(category, entries))
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
        f"{_ticker_sections(data)}"
        f"{render_stale_summary(stale)}"
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
```

- [ ] **Step 4: Esegui i test per verificare che passino**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_report_html -v`
Expected: PASS (12 test)

- [ ] **Step 5: Genera la pagina dal output reale**

Run: `cd src && ../.venv/bin/python -c "from report_html import render; print(render('../config.yaml'))"`
Expected: stampa `output/report.html` e crea il file (il path reale è `../output/report.html`).

- [ ] **Step 6: (Niente commit — progetto non è un repo git)**

---

### Task 2: Documentazione — README + technical-domain

**Files:**
- Modify: `README.md`
- Modify: `.opencode/context/project-intelligence/technical-domain.md`

**Interfaces:**
- Consumes: niente
- Produces: documentazione dello script + nota manutenibilità

- [ ] **Step 1: Aggiungi la sezione "Report HTML statico" al README.md** (dopo "Come aggiungere un nuovo scraper", prima di "Test")

```markdown
## Report HTML statico

Genera una pagina HTML statica (dark theme con toggle light) con l'output
consolidato: card per gli indicatori di mercato, tabelle per settore con
indicatori tecnici e semafori, date di ultimo aggiornamento.

```bash
cd src
../.venv/bin/python -c "from report_html import render; render('../config.yaml')"
```

Il file viene scritto in `output/report.html`. La funzione accetta un override:

```bash
../.venv/bin/python -c "from report_html import render; render('../config.yaml', '/tmp/report.html')"
```

> **⚠️ Manutenibilità**: quando aggiungi un nuovo scraper/modulo, **aggiorna
> `src/report_html.py`** (render_market_cards / _ticker_sections / render_ticker_table)
> per renderizzarlo nella pagina. Aggiungi anche un test in `test_report_html.py`.
```

- [ ] **Step 2: Aggiorna la struttura progetto nel README** (aggiungi i file sotto `src/`)

```markdown
    ├── report_html.py              # Genera pagina HTML statica (output/report.html)
```

- [ ] **Step 3: Aggiorna `technical-domain.md`** — Codebase References

```markdown
**Report HTML**: `src/report_html.py` — pagina statica da output.json (dark+light, semafori); aggiornare ad ogni nuovo scraper
```

- [ ] **Step 4: Esegui la suite completa**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS (69 test — 57 esistenti + 12 nuovi)

- [ ] **Step 5: (Niente commit — progetto non è un repo git)**
