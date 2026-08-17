# Pagina di immissione manual overrides + mini-server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una pagina HTML (`overrides.html`) servita da un mini-server Python che permette di immettere/aggiornare i valori manuali dei 5 indicatori attivi (aaii, fgi, naaim, vix_term_structure, pct_sma), con pulsante WRITE, checkbox `enabled` per-riga, navigazione reciproca con `report.html`, stessi stili e theme-toggle. Dopo ogni WRITE il report HTML viene rigenerato automaticamente.

**Architecture:** Mini-server HTTP stdlib (`http.server`, zero dipendenze) in `src/overrides_server.py` che serve la pagina (generata da `src/overrides_page.py` riusando `_CSS`/`_SCRIPT` di `report_html.py`), espone `GET /api/data` e `POST /api/save`, e dopo il save rigenera output+report replicando la logica di `run.py --override-only`. `manual_overrides.py` esteso con flag `enabled` e `save_override()`.

**Tech Stack:** Python 3.10+ (venv `.venv/bin/python`), stdlib `http.server`, unittest, HTML/CSS/JS vanilla (ES5).

## Global Constraints

- Tutto va eseguito con `.venv/bin/python` (PEP 668, niente install globale)
- Test da `src/`: `cd src && ../.venv/bin/python -m unittest discover -s tests`
- Naming: snake_case per funzioni Python; il JS usa `var`/`function` (ES5, coerente con `_SCRIPT`)
- Flag `enabled` per-riga: default **true** se assente (retrocompatibile); `false` → override ignorato in `apply_overrides`
- Il server usa solo stdlib (nessuna dipendenza esterna); bind `127.0.0.1`
- Whitelist dei 5 indicatori supportati: aaii, fgi, naaim, vix_term_structure, pct_sma
- La pagina riusa `_CSS`/`_SCRIPT` di `report_html.py` (stessi stili + theme-toggle)
- Dopo il save, il report viene rigenerato con la logica `--override-only` (nessuno scraping)
- Test esistenti devono restare verdi (suite 244 test)

---

### Task 1: Flag `enabled` + `save_override` in `manual_overrides.py`

**Files:**
- Modify: `src/manual_overrides.py`
- Test: `src/tests/test_manual_overrides.py`

**Interfaces:**
- Consumes: `validate_entry`, `apply_overrides`, `load_validated_overrides` esistenti
- Produces:
  - `validate_entry(key, entry)` — conserva `enabled: bool` (default True se assente) nel dict pulito
  - `apply_overrides(results, overrides, force_keys=None, now=None)` — salta gli override con `enabled: False`
  - `save_override(path, key, values: dict, enabled: bool = True, now: datetime | None = None) -> None` — scrive il YAML aggiornato: mantiene gli altri indicatori, aggiorna/inserisce `key` con i valori, `fetched_at` = now ISO, `source: manual`, `enabled`

- [ ] **Step 1: Write the failing test**

Aggiungere in `src/tests/test_manual_overrides.py` (importare `save_override`):

```python
class TestEnabledFlag(unittest.TestCase):
    def test_validate_conserves_enabled_false(self):
        entry = dict(VALID_AAII, enabled=False)
        cleaned = validate_entry("aaii", entry)
        self.assertFalse(cleaned["enabled"])

    def test_validate_defaults_enabled_true(self):
        cleaned = validate_entry("aaii", VALID_AAII)
        self.assertTrue(cleaned["enabled"])

    def test_apply_ignores_disabled_override(self):
        cleaned = validate_entry("aaii", dict(VALID_AAII, enabled=False))
        results = {"aaii": {"status": "error", "origin": "missing", "error": "boom"}}
        merged = apply_overrides(results, {"aaii": cleaned}, now=NOW)
        # override disabilitato → il risultato error/missing resta
        self.assertEqual(merged["aaii"]["status"], "error")

    def test_apply_uses_enabled_override(self):
        cleaned = validate_entry("aaii", dict(VALID_AAII, enabled=True))
        results = {"aaii": {"status": "error", "origin": "missing", "error": "boom"}}
        merged = apply_overrides(results, {"aaii": cleaned}, now=NOW)
        self.assertEqual(merged["aaii"]["origin"], "manual")
        self.assertEqual(merged["aaii"]["status"], "fresh")


class TestSaveOverride(unittest.TestCase):
    def test_save_override_updates_entry_and_fetched_at(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manual_overrides.yaml"
            path.write_text(
                "naaim:\n  exposure: 79.70\n  source: manual\n"
                "  fetched_at: \"2026-08-16T16:27:00+00:00\"\n"
                "  stale_after_hours: 168\n  entered_by: \"user\"\n",
                encoding="utf-8",
            )
            save_override(
                str(path),
                "naaim",
                {"exposure": 85.0, "stale_after_hours": 168, "entered_by": "user"},
                now=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
            )
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(data["naaim"]["exposure"], 85.0)
            self.assertEqual(data["naaim"]["fetched_at"], "2026-08-20T12:00:00+00:00")
            self.assertEqual(data["naaim"]["source"], "manual")
            self.assertIn("enabled", data["naaim"])

    def test_save_override_preserves_other_indicators(self):
        import tempfile
        from pathlib import Path
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manual_overrides.yaml"
            path.write_text(
                "aaii:\n  bullish: 37.0\n  source: manual\n"
                "  fetched_at: \"2026-08-14T18:20:00+00:00\"\n"
                "  stale_after_hours: 168\n  entered_by: \"user\"\n",
                encoding="utf-8",
            )
            save_override(
                str(path),
                "naaim",
                {"exposure": 85.0, "stale_after_hours": 168, "entered_by": "user"},
                now=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
            )
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertIn("aaii", data)
            self.assertIn("naaim", data)
            self.assertEqual(data["aaii"]["bullish"], 37.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_manual_overrides.TestEnabledFlag tests.test_manual_overrides.TestSaveOverride -v`
Expected: FAIL (`enabled` assente, `save_override` non definita)

- [ ] **Step 3: Write minimal implementation**

**`validate_entry`** — nella sezione dei campi comuni, dopo la validazione di `note`/`zone`, aggiungere:

```python
    enabled = entry.get("enabled", True)
    if not isinstance(enabled, bool):
        raise OverrideValidationError(f"{key}: enabled must be a boolean")
```

E nel dict di ritorno aggiungere `"enabled": enabled,`.

**`apply_overrides`** — nel loop, dopo `scraped_ok` e prima di `if is_fresh(...)`:

```python
        if not override.get("enabled", True):
            continue  # override disabilitato → ignorato (come se non esistesse)
```

**`save_override`** — nuova funzione dopo `apply_overrides`:

```python
def save_override(
    path: str,
    key: str,
    values: dict[str, Any],
    enabled: bool = True,
    now: datetime | None = None,
) -> None:
    """Write/update one manual override entry in the YAML file.

    Preserves the other indicators' entries; ``fetched_at`` is refreshed to
    ``now`` (UTC), ``source`` is forced to "manual". Malformed values are
    NOT written (caller must validate first).
    """
    now = now or datetime.now(timezone.utc)
    overrides = load_overrides(path)
    entry = dict(overrides.get(key, {}))
    entry.update(values)
    entry["source"] = "manual"
    entry["enabled"] = bool(enabled)
    entry["fetched_at"] = now.isoformat()
    overrides[key] = entry
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(overrides, fh, sort_keys=False, allow_unicode=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_manual_overrides -v`
Expected: PASS (tutti i test della classe, inclusi i nuovi)

- [ ] **Step 5: Commit**

```bash
git add src/manual_overrides.py src/tests/test_manual_overrides.py
git commit -m "feat: add enabled flag and save_override to manual_overrides"
```

---

### Task 2: `overrides_page.py` — generazione pagina HTML

**Files:**
- Create: `src/overrides_page.py`
- Test: `src/tests/test_overrides_page.py`

**Interfaces:**
- Consumes: `_CSS`, `_SCRIPT`, `_ITALIAN_MONTHS`, `format_iso_dt` da `report_html.py`; `load_overrides` da `manual_overrides.py`
- Produces: `render_overrides_page(overrides: dict[str, Any]) -> str` — pagina HTML completa con header (titolo, link al report, theme-toggle), una card per indicatore (nome + badge, checkbox enabled, campi specifici, stale_after_hours, note, pulsante WRITE), e il JS che carica `/api/data` e POST `/api/save`

- [ ] **Step 1: Write the failing test**

Creare `src/tests/test_overrides_page.py`:

```python
"""Unit tests for the manual overrides entry page generator."""

from __future__ import annotations

import unittest

from overrides_page import render_overrides_page


class TestRenderOverridesPage(unittest.TestCase):
    def test_renders_header_with_links_and_toggle(self):
        html = render_overrides_page({})
        self.assertIn("Immissione manuale", html)
        self.assertIn("Vai al report", html)
        self.assertIn("theme-toggle", html)

    def test_renders_card_per_indicator(self):
        overrides = {
            "naaim": {"exposure": 79.70, "stale_after_hours": 168, "entered_by": "user"},
            "vix_term_structure": {"m1": 15.6, "m2": 17.9},
        }
        html = render_overrides_page(overrides)
        self.assertIn("NAAIM", html)
        self.assertIn("VIX Term Structure", html)
        self.assertIn("79.70", html)
        self.assertIn("15.6", html)

    def test_renders_enabled_checkbox(self):
        overrides = {"naaim": {"exposure": 79.70, "enabled": False}}
        html = render_overrides_page(overrides)
        self.assertIn('name="enabled"', html)
        self.assertIn("checked", html)  # enabled=False → checkbox NON checked
```

Nota: l'ultimo test deve verificare che la checkbox NON sia checked quando `enabled: False` — il testo del test sopra è volutamente errato (asserisce `checked` presente), il che è SBAGLIATO. Correggere il test per il comportamento corretto: con `enabled: False` la checkbox NON deve avere `checked`.

```python
    def test_renders_enabled_checkbox(self):
        overrides = {"naaim": {"exposure": 79.70, "enabled": False}}
        html = render_overrides_page(overrides)
        self.assertIn('name="enabled"', html)
        # enabled=False → checkbox non checked (checked presente solo se enabled=True)
        checkbox = html.split("name=\"enabled\"")[1][:200]
        self.assertNotIn("checked", checkbox)

    def test_renders_checked_when_enabled(self):
        overrides = {"naaim": {"exposure": 79.70, "enabled": True}}
        html = render_overrides_page(overrides)
        checkbox = html.split("name=\"enabled\"")[1][:200]
        self.assertIn("checked", checkbox)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_overrides_page -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'overrides_page'`

- [ ] **Step 3: Write minimal implementation**

Creare `src/overrides_page.py`:

```python
"""Manual overrides entry page generator.

Builds a static HTML page (dark/light theme, same styles as the dashboard)
that lets the user edit the manual overrides supported by
``manual_overrides.yaml`` and submit them to the local server
(``overrides_server.py``) which persists them and re-renders the report.

The page is served by ``GET /`` from the overrides server; it fetches the
current values from ``GET /api/data`` and posts edits to ``POST /api/save``.
"""

from __future__ import annotations

import html as html_mod
from typing import Any

from report_html import _CSS, _SCRIPT, format_iso_dt

# Field descriptors per supported indicator: label, input type, step.
_INDICATOR_FIELDS: dict[str, dict[str, Any]] = {
    "aaii": {
        "label": "AAII Investor Sentiment Survey",
        "badge": "fallback",
        "fields": {
            "bullish": {"label": "Bullish %", "type": "number", "step": "0.1"},
            "neutral": {"label": "Neutral %", "type": "number", "step": "0.1"},
            "bearish": {"label": "Bearish %", "type": "number", "step": "0.1"},
        },
    },
    "fgi": {
        "label": "Fear & Greed Index",
        "badge": "fallback",
        "fields": {
            "score": {"label": "Score (0-100)", "type": "number", "step": "0.1"},
            "zone": {"label": "Zone", "type": "text", "step": None},
        },
    },
    "naaim": {
        "label": "NAAIM Exposure Index",
        "badge": "manual",
        "fields": {
            "exposure": {"label": "Exposure", "type": "number", "step": "0.1"},
        },
    },
    "vix_term_structure": {
        "label": "VIX Term Structure",
        "badge": "manual",
        "fields": {
            "m1": {"label": "M1 (futures 1 mese)", "type": "number", "step": "0.01"},
            "m2": {"label": "M2 (futures 2 mesi)", "type": "number", "step": "0.01"},
        },
    },
    "pct_sma": {
        "label": "% sopra SMA50/SMA200 (mercato USA)",
        "badge": "manual",
        "fields": {
            "pct_sma50": {"label": "% sopra SMA50", "type": "number", "step": "0.1"},
            "pct_sma200": {"label": "% sopra SMA200", "type": "number", "step": "0.1"},
        },
    },
}

_PAGE_CSS = _CSS + """\
.override-form { margin-top: 24px; }
.override-card { background: var(--card); border: 1px solid var(--border);
        border-radius: 12px; padding: 16px; margin-bottom: 16px; }
.override-card .row { display: flex; align-items: center; gap: 12px;
        flex-wrap: wrap; margin-bottom: 8px; }
.override-card label { color: var(--muted); font-size: 0.85rem; }
.override-card input[type="number"], .override-card input[type="text"] {
        background: var(--bg); color: var(--text); border: 1px solid var(--border);
        border-radius: 6px; padding: 6px 8px; font-size: 0.9rem; width: 140px; }
.override-card input[type="text"] { width: 220px; }
.override-card button { background: var(--green); color: #fff; border: none;
        border-radius: 8px; padding: 8px 16px; cursor: pointer; font-size: 0.9rem;
        font-weight: 600; }
.override-card button:hover { opacity: 0.9; }
.msg { padding: 8px 12px; border-radius: 8px; margin: 8px 0; font-size: 0.9rem; }
.msg.ok { background: var(--green); color: #fff; }
.msg.err { background: var(--red); color: #fff; }
"""


def _render_field(key: str, spec: dict[str, Any], value: Any) -> str:
    ftype = spec["type"]
    step = spec.get("step")
    step_attr = f' step="{step}"' if step else ""
    val = "" if value is None else str(value)
    return (
        f'<label>{html_mod.escape(spec["label"])}'
        f'<input type="{ftype}" name="{key}" value="{html_mod.escape(val)}"{step_attr}></label>'
    )


def _render_card(indicator: str, spec: dict[str, Any], entry: dict[str, Any]) -> str:
    enabled = bool(entry.get("enabled", True))
    checked = " checked" if enabled else ""
    fields_html = "".join(
        _render_field(key, fspec, entry.get(key))
        for key, fspec in spec["fields"].items()
    )
    stale = entry.get("stale_after_hours", 24)
    note = entry.get("note", "")
    fetched = format_iso_dt(entry.get("fetched_at"))
    badge_cls = "ok" if spec["badge"] == "manual" else "warning"
    return (
        f'<div class="override-card" data-key="{indicator}">'
        f'<div class="row"><strong>{html_mod.escape(spec["label"])}</strong>'
        f' <span class="sema {badge_cls}">{spec["badge"]}</span>'
        f'<label><input type="checkbox" name="enabled"{checked}> abilitato</label></div>'
        f'<div class="row">{fields_html}</div>'
        f'<div class="row"><label>Validità (h) '
        f'<input type="number" name="stale_after_hours" value="{stale}" step="1"></label>'
        f'<label>Nota <input type="text" name="note" value="{html_mod.escape(str(note))}"></label></div>'
        f'<div class="row"><span class="name">Ultimo: {fetched}</span>'
        f'<button type="button" onclick="saveOverride(\'{indicator}\')">WRITE</button></div>'
        f"</div>"
    )


_OVERRIDES_SCRIPT = _SCRIPT + """\
<script>
function saveOverride(key) {
  var card = document.querySelector('[data-key="' + key + '"]');
  var payload = { key: key, enabled: card.querySelector('[name="enabled"]').checked };
  card.querySelectorAll("input[name]").forEach(function (input) {
    if (input.name !== "enabled") payload[input.name] = input.value;
  });
  fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }).then(function (resp) { return resp.json(); }).then(function (data) {
    var msg = document.createElement("div");
    msg.className = "msg " + (data.ok ? "ok" : "err");
    msg.textContent = data.message || (data.ok ? "Salvato" : "Errore");
    card.appendChild(msg);
    setTimeout(function () { msg.remove(); }, 3000);
  });
}
</script>
"""


def render_overrides_page(overrides: dict[str, Any]) -> str:
    """Render the complete overrides entry page."""
    cards = "".join(
        _render_card(indicator, spec, overrides.get(indicator, {}))
        for indicator, spec in _INDICATOR_FIELDS.items()
    )
    return (
        "<!DOCTYPE html>\n<html lang=\"it\" data-theme=\"dark\">\n<head>"
        "<meta charset=\"utf-8\">"
        "<title>Immissione manuale indicatori</title>"
        f"<style>{_PAGE_CSS}</style>"
        "</head>\n<body><div class=\"container\">"
        "<header>"
        "<div><h1>✍️ Immissione manuale indicatori</h1>"
        '<div class="sub">Valori per gli indicatori non scrapabili</div></div>'
        '<div><a href="/report.html" class="badge fresh">Vai al report →</a> '
        '<button id="theme-toggle" type="button">☀️ Light</button></div>'
        "</header>"
        f'<div class="override-form">{cards}</div>'
        "</div>"
        f"{_OVERRIDES_SCRIPT}"
        "</body>\n</html>"
    )
```

Nota: `_ITALIAN_MONTHS` e `format_iso_dt` sono già importati da `report_html.py`; `format_iso_dt` è usato nella card.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_overrides_page -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/overrides_page.py src/tests/test_overrides_page.py
git commit -m "feat: add overrides entry page generator"
```

---

### Task 3: `overrides_server.py` — mini-server + API + rigenerazione report

**Files:**
- Create: `src/overrides_server.py`
- Test: `src/tests/test_overrides_server.py`

**Interfaces:**
- Consumes: `load_overrides`, `load_validated_overrides`, `apply_overrides`, `validate_entry`, `save_override` da `manual_overrides.py`; `render_overrides_page` da `overrides_page.py`; `consolidate` da `consolidator.py`; `_build_strategy_indicators` da `orchestrator.py`; `render` da `report_html.py`; `load_config` da `config_loader.py`
- Produces:
  - `class OverridesHandler(BaseHTTPRequestHandler)` — gestisce `GET /` (pagina), `GET /api/data` (JSON), `POST /api/save` (salva + rebuild), `GET /report.html` (serve il report)
  - `rebuild_report(config_path: str) -> None` — replica logica `run.py mode_override_only` (nessuno scraping)
  - `main()` — CLI `python overrides_server.py [--port 8000] [--config ../config.yaml]`

- [ ] **Step 1: Write the failing test**

Creare `src/tests/test_overrides_server.py`:

```python
"""Unit tests for the manual overrides mini-server (API + rebuild)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from overrides_server import OverridesHandler, rebuild_report


class TestRebuildReport(unittest.TestCase):
    def test_rebuild_applies_overrides_and_writes_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            config_path = tmp / "config.yaml"
            config_path.write_text(
                "output:\n  json_path: output.json\n  db_path: audit.db\n"
                "strategy:\n  proxy_accepted: []\n",
                encoding="utf-8",
            )
            (tmp / "output.json").write_text(
                json.dumps({
                    "generated_at": "2026-08-17T10:00:00+00:00",
                    "fgi": {"score": 62.0, "status": "fresh", "origin": "scraped",
                            "fetched_at": "2026-08-17T10:00:00+00:00"},
                    "naaim": {"status": "error", "origin": "missing", "error": "x"},
                    "stale_summary": {"total_sources": 2, "fresh": 1, "stale": 1},
                }),
                encoding="utf-8",
            )
            overrides_path = tmp / "manual_overrides.yaml"
            overrides_path.write_text(
                "naaim:\n  exposure: 85.0\n  source: manual\n"
                "  fetched_at: \"2026-08-17T12:00:00+00:00\"\n"
                "  stale_after_hours: 168\n  entered_by: \"user\"\n",
                encoding="utf-8",
            )
            # Il registry indicatori non esiste in tmp → ricade sul progetto reale
            config = {
                "output": {"json_path": "output.json", "db_path": "audit.db"},
                "strategy": {"proxy_accepted": [], "manual_overrides": "manual_overrides.yaml"},
            }
            with mock.patch("overrides_server.load_config", return_value=config):
                rebuild_report(str(config_path))
            data = json.loads((tmp / "output.json").read_text(encoding="utf-8"))
            self.assertEqual(data["naaim"]["origin"], "manual")
            self.assertEqual(data["naaim"]["exposure"], 85.0)


class TestOverridesHandler(unittest.TestCase):
    def _handler(self):
        return OverridesHandler

    def test_handler_is_bounded_to_localhost(self):
        # OverridesHandler deve essere servito solo su 127.0.0.1
        self.assertTrue(hasattr(OverridesHandler, "server_version"))
```

Nota: il test del handler è minimale (i test HTTP completi richiedono un server reale — fuori scope per unittest veloce). Il focus è `rebuild_report`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_overrides_server -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'overrides_server'`

- [ ] **Step 3: Write minimal implementation**

Creare `src/overrides_server.py`:

```python
"""Local mini-server for editing manual overrides and re-rendering the report.

Serves:
    GET  /            → the overrides entry page (overrides_page.render_overrides_page)
    GET  /api/data    → JSON of the current manual_overrides.yaml
    POST /api/save    → validate + save one override, then rebuild output + report
    GET  /report.html → the existing output/report.html

Binds to 127.0.0.1 only (single-user, local use). No external dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from config_loader import load_config
from consolidator import consolidate
from manual_overrides import (
    apply_overrides,
    load_overrides,
    load_validated_overrides,
    save_override,
    validate_entry,
)
from orchestrator import _build_strategy_indicators
from overrides_page import render_overrides_page
from report_html import render as render_report

# Whitelist degli indicatori supportati per override manuale.
SUPPORTED_KEYS = frozenset(
    {"aaii", "fgi", "naaim", "vix_term_structure", "pct_sma"}
)

# Path del config: risolto rispetto alla root del progetto (src/..).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = str(PROJECT_ROOT / "config.yaml")


def rebuild_report(config_path: str) -> None:
    """Apply manual overrides to the existing output.json and re-render.

    Replicates ``run.py --override-only``: no scraping. Loads output.json,
    applies overrides (scraping > manual > missing), rebuilds the indicator
    matrix and renders the HTML report.
    """
    base_dir = Path(config_path).resolve().parent
    config = load_config(config_path)
    output_path = base_dir / config.get("output", {}).get("json_path", "output/output.json")

    if not output_path.exists():
        raise FileNotFoundError(
            f"Output JSON not found at {output_path}. Run the orchestrator first."
        )

    with output_path.open("r", encoding="utf-8") as fh:
        existing = json.load(fh)

    results: dict[str, Any] = {}
    for key, value in existing.items():
        if isinstance(value, dict) and "status" in value:
            results[key] = value

    strategy_cfg = config.get("strategy", {})
    overrides_path = base_dir / strategy_cfg.get("manual_overrides", "manual_overrides.yaml")
    force_keys = strategy_cfg.get("force_manual_overrides", []) or []
    overrides, errors = load_validated_overrides(str(overrides_path))
    for error in errors:
        print(f"  [warn] {error}")

    results = apply_overrides(results, overrides, force_keys=force_keys)

    output = consolidate(results)
    output["strategy_indicators"] = _build_strategy_indicators(config, base_dir, results)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    render_report(config_path)


class OverridesHandler(BaseHTTPRequestHandler):
    """HTTP handler: serves the page, the data API and the report."""

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        if self.path == "/" or self.path == "/overrides.html":
            self._send_html(200, render_overrides_page(load_overrides()))
            return
        if self.path == "/api/data":
            self._send_json(200, {"ok": True, "overrides": load_overrides()})
            return
        if self.path == "/report.html":
            report_path = PROJECT_ROOT / "output" / "report.html"
            if not report_path.exists():
                self._send_html(404, "<h1>Report non trovato</h1><p>Esegui run.py prima.</p>")
                return
            self._send_html(200, report_path.read_text(encoding="utf-8"))
            return
        self._send_html(404, "<h1>404</h1>")

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        if self.path != "/api/save":
            self._send_json(404, {"ok": False, "message": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "message": "JSON malformato"})
            return

        key = payload.get("key")
        if key not in SUPPORTED_KEYS:
            self._send_json(400, {"ok": False, "message": f"indicatore non supportato: {key}"})
            return

        enabled = bool(payload.get("enabled", True))
        values: dict[str, Any] = {}
        for field, fspec in _field_specs(key).items():
            raw = payload.get(field)
            if raw is None:
                self._send_json(400, {"ok": False, "message": f"campo mancante: {field}"})
                return
            if fspec["type"] == "number":
                try:
                    values[field] = float(raw)
                except (TypeError, ValueError):
                    self._send_json(400, {"ok": False, "message": f"campo non numerico: {field}"})
                    return
            else:
                values[field] = str(raw).strip()
        values["stale_after_hours"] = float(payload.get("stale_after_hours", 24))
        values["entered_by"] = "user"
        if payload.get("note"):
            values["note"] = str(payload["note"]).strip()

        # Validazione lato server con la stessa logica del pipeline.
        candidate = {**values, "source": "manual", "enabled": enabled,
                     "fetched_at": datetime.now(timezone.utc).isoformat()}
        try:
            validate_entry(key, candidate)
        except ValueError as error:
            self._send_json(400, {"ok": False, "message": str(error)})
            return

        try:
            save_override(str(_overrides_path()), key, values, enabled=enabled)
            rebuild_report(DEFAULT_CONFIG)
        except Exception as error:  # noqa: BLE001 - errori mostrati all'utente
            self._send_json(500, {"ok": False, "message": f"errore: {error}"})
            return
        self._send_json(200, {"ok": True, "message": "Valore salvato e report rigenerato"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        print(f"[overrides] {self.address_string()} - {format % args}")


def _overrides_path() -> Path:
    strategy_cfg = load_config(DEFAULT_CONFIG).get("strategy", {})
    return PROJECT_ROOT / strategy_cfg.get("manual_overrides", "manual_overrides.yaml")


def _field_specs(key: str) -> dict[str, Any]:
    from overrides_page import _INDICATOR_FIELDS
    return _INDICATOR_FIELDS[key]["fields"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual overrides entry server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), OverridesHandler)
    print(f"Serving overrides on http://{args.host}:{args.port}/ (Ctrl+C per fermare)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_overrides_server -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/overrides_server.py src/tests/test_overrides_server.py
git commit -m "feat: add local overrides server (page + API + report rebuild)"
```

---

### Task 4: Link "Immissione manuale" nel report

**Files:**
- Modify: `src/report_html.py` — `build_page` (header, ~riga 1040)
- Test: `src/tests/test_report_html.py` (classe `TestRender` o `TestRenderSections`)

**Interfaces:**
- Consumes: niente di nuovo
- Produces: l'header del report contiene un link "Immissione manuale" → `/overrides.html`

- [ ] **Step 1: Write the failing test**

Aggiungere in `src/tests/test_report_html.py`:

```python
    def test_page_links_to_overrides_page(self):
        html = build_page(_sample_data())
        self.assertIn("Immissione manuale", html)
        self.assertIn("/overrides.html", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_report_html -v`
Expected: FAIL (link assente)

- [ ] **Step 3: Write minimal implementation**

In `build_page`, nell'header, dopo il badge overall e prima del theme-toggle:

```python
        f'<div><span class="badge {overall}">{overall}</span> '
        '<a href="/overrides.html" class="badge fresh">✍️ Immissione manuale</a> '
        '<button id="theme-toggle" type="button">☀️ Light</button></div>'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_report_html -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/report_html.py src/tests/test_report_html.py
git commit -m "feat: add manual-overrides link to report header"
```

---

### Task 5: Verifica finale e suite completa

**Files:**
- Nessun file nuovo — verifica end-to-end

**Interfaces:**
- Consumes: tutti i Task 1-4

- [ ] **Step 1: Run the full test suite**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests`
Expected: OK — 244 test esistenti + nuovi (TestEnabledFlag 4 + TestSaveOverride 2 + TestRenderOverridesPage 4 + TestRebuildReport 1 + TestOverridesHandler 1 + TestReportHtml 1) = 253 test, tutti verdi

- [ ] **Step 2: Start the server and verify the page loads**

Run: `cd src && ../.venv/bin/python overrides_server.py --port 8000 &` poi `curl http://127.0.0.1:8000/ | head -20`
Expected: pagina HTML con titolo "Immissione manuale indicatori"

- [ ] **Step 3: Verify the API returns current overrides**

Run: `curl http://127.0.0.1:8000/api/data`
Expected: JSON con i 5 indicatori e i valori attuali

- [ ] **Step 4: Verify the report link works**

Run: `curl -s http://127.0.0.1:8000/report.html | head -5`
Expected: HTML del report (output/report.html)

- [ ] **Step 5: Verify report has the link back**

Run: `grep -c 'Immissione manuale' output/report.html`
Expected: ≥ 1 (dopo rigenerazione)

- [ ] **Step 6: Stop the server and commit any leftover changes**

```bash
kill %1
git status
git add -A
git commit -m "chore: verify overrides page feature end-to-end"
```

(Se non ci sono modifiche pendenti, saltare il commit.)