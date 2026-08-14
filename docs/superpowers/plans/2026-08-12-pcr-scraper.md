# PCR Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementare `pcr_scraper.py` (Equity Put/Call Ratio da CBOE daily market statistics) e integrarlo nel report HTML come card macro con semaforo e legenda.

**Architecture:** Modulo scraper che segue il contratto `run(config) -> dict` (pattern fgi/vix): `fetch_page` (DI rete) → `parse_ratios` (funzione pura, de-escaping JSON embeddata) → `build_result` (formato file.json). Il PCR è indicatore macro: card nel report, NON entra in compute_signal.

**Tech Stack:** Python 3.14 (venv), requests, stdlib (re, json)

## Global Constraints

- **Venv obbligatorio**: `../.venv/bin/python` (da src/).
- Contratto scraper `run(config) -> dict` con funzioni pure + DI per la rete.
- Type hints, snake_case, errori `ValueError` descrittivi.
- Fonte: CBOE daily market statistics (Barchart inaccessibile → CBOE ufficiale).
- **compute_signal NON cambia** — il PCR è conferma macro, non scoring ticker.
- **Il progetto NON è un repo git** → i passi "Commit" vanno saltati.
- Test suite: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`.

---

### Task 1: `pcr_scraper.py` — modulo + test

**Files:**
- Create: `src/scrapers/pcr_scraper.py`
- Create: `src/tests/test_pcr_scraper.py`

**Interfaces:**
- Consumes: `config` (url, timeout, retries, backoff, headers, stale_after_hours)
- Produces:
  - `parse_ratios(html: str) -> dict` — estrae equity_pcr/total_pcr/index_pcr/trade_date
  - `build_result(data: dict, fetched_at: str | None = None) -> dict`
  - `fetch_page(session, url, timeout) -> str`
  - `run(config: dict | None = None) -> dict`

- [ ] **Step 1: Scrivi i test falliti in `src/tests/test_pcr_scraper.py`**

```python
"""Unit tests for the PCR scraper (pure functions, no network)."""

from __future__ import annotations

import unittest

from scrapers.pcr_scraper import build_result, parse_ratios

# HTML mock con il JSON embeddata escapato come da CBOE (Next.js __next_f)
_HTML_SAMPLE = """
<script>self.__next_f.push([1,"24:[\\"$\\",\\"$L32\\",null,{\\"data\\":{\\"optionsData\\":{\\"ratios\\":[{\\"name\\":\\"TOTAL PUT/CALL RATIO\\",\\"value\\":\\"0.81\\"},{\\"name\\":\\"INDEX PUT/CALL RATIO\\",\\"value\\":\\"0.90\\"},{\\"name\\":\\"EXCHANGE TRADED PRODUCTS PUT/CALL RATIO\\",\\"value\\":\\"0.87\\"},{\\"name\\":\\"EQUITY PUT/CALL RATIO\\",\\"value\\":\\"0.63\\"},{\\"name\\":\\"CBOE VOLATILITY INDEX (VIX) PUT/CALL RATIO\\",\\"value\\":\\"0.20\\"}]},\\"selectedDate\\":\\"2026-08-11\\",\\"minDate\\":\\"2019-10-07\\"}]"])</script>
"""


class TestParseRatios(unittest.TestCase):
    def test_parses_equity_pcr(self):
        data = parse_ratios(_HTML_SAMPLE)
        self.assertEqual(data["equity_pcr"], 0.63)
        self.assertEqual(data["total_pcr"], 0.81)
        self.assertEqual(data["index_pcr"], 0.90)
        self.assertEqual(data["trade_date"], "2026-08-11")

    def test_missing_ratios_raises(self):
        with self.assertRaises(ValueError):
            parse_ratios("<html><body>no data here</body></html>")


class TestBuildResult(unittest.TestCase):
    def test_builds_file_json_shape(self):
        data = {"equity_pcr": 0.63, "total_pcr": 0.81, "index_pcr": 0.90,
                "trade_date": "2026-08-11"}
        result = build_result(data, fetched_at="2026-08-12T00:00:00+00:00")
        self.assertEqual(result["equity_pcr"], 0.63)
        self.assertEqual(result["trade_date"], "2026-08-11")
        self.assertEqual(result["frequency"], "daily")
        self.assertEqual(result["stale_after_hours"], 24)
        self.assertEqual(result["status"], "fresh")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Esegui i test per verificare che falliscano**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_pcr_scraper -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scrapers.pcr_scraper'`

- [ ] **Step 3: Implementa `src/scrapers/pcr_scraper.py`**

```python
"""Equity Put/Call Ratio scraper module.

Fetches the CBOE daily market statistics page and extracts the EQUITY PUT/CALL
RATIO (plus total and index ratios for context). The page embeds the data as an
escaped JSON string in a Next.js ``__next_f`` payload, which is de-escaped and
parsed. Returns a dict in the file.json output format.

NOTE: the strategy originally targeted Barchart, but Barchart is not scrapable
(WAF 404). CBOE is the official primary source of the data Barchart aggregates.

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

CBOE_DAILY_URL = "https://www.cboe.com/us/options/market_statistics/daily/"

DEFAULT_TIMEOUT = 20
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 2.0
DEFAULT_STALE_AFTER_HOURS = 24
FREQUENCY = "daily"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def parse_ratios(html: str) -> dict[str, Any]:
    """Extract put/call ratios from the CBOE daily market statistics page.

    The data lives in an escaped JSON string inside a ``__next_f`` push.
    Returns a dict with equity_pcr, total_pcr, index_pcr and trade_date.

    Raises:
        ValueError: If the ratios block cannot be found or parsed.
    """
    # Primary: extract the escaped ratios array.
    m = re.search(r'\\"optionsData\\":\{.*?\\"ratios\\":\[(.*?)\]\}', html, re.S)
    if m:
        clean = m.group(1).replace('\\"', '"').replace('\\\\', '')
        rows = json.loads(f"[{clean}]")
    else:
        # Fallback: direct regex on the escaped equity entry.
        m2 = re.search(r'\\"EQUITY PUT/CALL RATIO\\",\\"value\\":\\"([\d.]+)\\"', html)
        if not m2:
            raise ValueError("CBOE page does not contain put/call ratio data")
        rows = [{"name": "EQUITY PUT/CALL RATIO", "value": m2.group(1)}]

    def _ratio(name: str) -> float | None:
        for row in rows:
            if row.get("name") == name:
                try:
                    return float(row["value"])
                except (KeyError, TypeError, ValueError):
                    return None
        return None

    trade_date: str | None = None
    m_date = re.search(r'\\"selectedDate\\":\\"(\d{4}-\d{2}-\d{2})\\"', html)
    if m_date:
        trade_date = m_date.group(1)

    return {
        "equity_pcr": _ratio("EQUITY PUT/CALL RATIO"),
        "total_pcr": _ratio("TOTAL PUT/CALL RATIO"),
        "index_pcr": _ratio("INDEX PUT/CALL RATIO"),
        "trade_date": trade_date,
    }


def build_result(
    data: dict[str, Any],
    fetched_at: str | None = None,
    stale_after_hours: int = DEFAULT_STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Build the output dict in the file.json format."""
    return {
        "equity_pcr": data.get("equity_pcr"),
        "total_pcr": data.get("total_pcr"),
        "index_pcr": data.get("index_pcr"),
        "trade_date": data.get("trade_date"),
        "fetched_at": fetched_at or _now_iso(),
        "frequency": FREQUENCY,
        "stale_after_hours": stale_after_hours,
        "status": "fresh",
    }


def fetch_page(
    session: requests.Session,
    url: str = CBOE_DAILY_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Fetch the CBOE daily market statistics page."""
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def _fetch_with_retry(
    session: requests.Session,
    url: str,
    timeout: int,
    retries: int,
    backoff: float,
) -> str:
    """Fetch the page with retry and exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return fetch_page(session, url=url, timeout=timeout)
        except (requests.RequestException, ValueError) as error:
            last_error = error
            logger.warning(
                "PCR fetch attempt %d/%d failed: %s", attempt + 1, retries, error
            )
            if attempt < retries - 1:
                time.sleep(backoff * (2**attempt))
    raise RuntimeError(f"PCR fetch failed after {retries} attempts: {last_error}")


def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch and return the equity put/call ratio as a structured dict.

    Args:
        config: Optional overrides (url, timeout, retries, backoff, headers).
    """
    config = config or {}
    url = config.get("url", CBOE_DAILY_URL)
    timeout = config.get("timeout", DEFAULT_TIMEOUT)
    retries = config.get("retries", DEFAULT_RETRIES)
    backoff = config.get("backoff", DEFAULT_BACKOFF)
    headers = config.get("headers", DEFAULT_HEADERS)

    with requests.Session() as session:
        session.headers.update(headers)
        html = _fetch_with_retry(session, url, timeout, retries, backoff)

    data = parse_ratios(html)
    return build_result(
        data,
        stale_after_hours=config.get("stale_after_hours", DEFAULT_STALE_AFTER_HOURS),
    )
```

- [ ] **Step 4: Esegui i test per verificare che passino**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_pcr_scraper -v`
Expected: PASS (3 test)

- [ ] **Step 5: Verifica con la pagina reale**

Run: `cd src && ../.venv/bin/python -c "from scrapers.pcr_scraper import run; print(run())"`
Expected: dict con `equity_pcr` reale (~0.6), `trade_date` reale

- [ ] **Step 6: (Niente commit — progetto non è un repo git)**

---

### Task 2: Config.yaml + Report HTML (card PCR)

**Files:**
- Modify: `config.yaml`
- Modify: `src/report_html.py`
- Modify: `src/tests/test_report_html.py`

**Interfaces:**
- Consumes: `pcr_scraper.run(config)` dal Task 1
- Produces: sezione `pcr` in config, card "Put/Call Ratio" nel report, semaforo, voce legenda

- [ ] **Step 1: Aggiungi `pcr` in config.yaml** (dopo vix, prima di ohlcv)

```yaml
  pcr:
    module: scrapers.pcr_scraper
    output_key: pcr
    schedule: daily
    config:
      url: "https://www.cboe.com/us/options/market_statistics/daily/"
      timeout: 20
      retries: 3
      backoff: 2.0
      headers:
        User-Agent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
      stale_after_hours: 24
```

- [ ] **Step 2: Aggiungi la card PCR in `render_market_cards`** (src/report_html.py)

Dopo la card VIX, aggiungi:
```python
    pcr = data.get("pcr", {})
    equity_pcr = pcr.get("equity_pcr")
    pcr_cls = "fear" if equity_pcr is not None and equity_pcr >= 0.80 else (
        "greed" if equity_pcr is not None and equity_pcr <= 0.70 else "neutral")
    pcr_badge = "" if pcr_cls == "neutral" else (
        f'<span class="sema {pcr_cls}">{pcr_cls}</span>')
    parts.append(
        '<div class="card"><div class="label">Equity Put/Call Ratio</div>'
        f'<div class="value">{fmt(equity_pcr)}</div>{pcr_badge}'
        f'<div class="meta">Giorno: {pcr.get("trade_date", "—")} · '
        f'Aggiornato: {format_iso_dt(pcr.get("fetched_at"))}</div></div>'
    )
```

- [ ] **Step 3: Aggiungi semafori PCR al CSS** (accanto a `.sema.*`)

```css
.sema.fear { background: var(--red); color: #fff; }
.sema.greed { background: var(--green); color: #fff; }
```

- [ ] **Step 4: Aggiungi la voce PCR in `_LEGEND_MARKET`** (src/report_html.py)

```python
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
```

- [ ] **Step 5: Aggiungi test report_html per PCR**

Nel file test, aggiorna `_sample_data()` per includere il modulo pcr e aggiungi:
```python
    def test_market_cards_contains_pcr(self):
        data = _sample_data()
        data["pcr"] = {"equity_pcr": 0.63, "trade_date": "2026-08-11",
                       "fetched_at": "2026-08-12T00:00:00+00:00"}
        html = render_market_cards(data)
        self.assertIn("Put/Call Ratio", html)
        self.assertIn("0.63", html)

    def test_pcr_legend_entry(self):
        html = render_legend()
        self.assertIn("Put/Call Ratio", html)
        self.assertIn("0.80", html)
```

- [ ] **Step 6: Esegui la suite completa**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS (test esistenti + nuovi pcr + report)

- [ ] **Step 7: (Niente commit — progetto non è un repo git)**

---

### Task 3: Documentazione — README + context

**Files:**
- Modify: `README.md`
- Modify: `.opencode/context/project-intelligence/scraping-patterns.md`
- Modify: `.opencode/context/project-intelligence/technical-domain.md`
- Modify: `.opencode/context/project-intelligence/navigation.md`

**Interfaces:**
- Consumes: niente
- Produces: documentazione del modulo PCR

- [ ] **Step 1: Aggiorna README.md** — tabella "Dove sono gli scraper" e "Stato dei moduli"

```markdown
| `pcr_scraper.py` | CBOE | Equity Put/Call Ratio | giornaliera (lag 1gg) |
```

E in Stato dei moduli:
```markdown
| `pcr_scraper.py` | ✅ Funzionante | Equity PCR da CBOE (Barchart sostituito: WAF 404). Soglia >0.80 fear. |
```

- [ ] **Step 2: Aggiorna scraping-patterns.md** — nuova sezione pattern PCR

```markdown
## PCR: JSON escapato CBOE (non Barchart!)
Barchart non è scrapabile (WAF 404). Usare CBOE daily market statistics: il dato
è in un JSON escapato dentro `__next_f.push`. Estrarre `EQUITY PUT/CALL RATIO`.
```python
m = re.search(r'\\"optionsData\\":\{.*?\\"ratios\\":\[(.*?)\]\}', html, re.S)
clean = m.group(1).replace('\\"', '"').replace('\\\\', '')
rows = json.loads(f'[{clean}]')
pcr = next(r["value"] for r in rows if r["name"] == "EQUITY PUT/CALL RATIO")
```
```

- [ ] **Step 3: Aggiorna technical-domain.md** — Codebase References + tabella

```markdown
**Scraper PCR**: `src/scrapers/pcr_scraper.py` — Equity PCR da CBOE (JSON escapato), Barchart sostituito (WAF 404)
```

- [ ] **Step 4: Aggiorna navigation.md** — log

```markdown
- **2026-08-12**: Aggiunto pcr_scraper.py (Equity PCR da CBOE) — spec/plan docs/superpowers; scraping-patterns.md aggiornato
```

- [ ] **Step 5: Esegui la suite completa**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 6: (Niente commit — progetto non è un repo git)**
