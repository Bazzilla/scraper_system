# PCT SMA Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementare `pct_sma_scraper.py` (breadth settoriale % sopra SMA50/SMA200 calcolata dai dati OHLCV locali), ampliare l'universo ticker a ~29, e aggiungere la card nel report HTML.

**Architecture:** Modulo che legge `output/ohlcv_cache.json` (scritto da `ohlcv_fetcher`), ricalcola SMA50/SMA200 dai record OHLCV (riusando `records_to_frame` di indicators.py), e aggrega la % di ticker sopra le SMA per categoria e totale. Segue il pattern di `indicators.py` (legge cache → calcola), NON è uno scraper di rete. La breadth è conferma macro — **non entra in compute_signal**.

**Tech Stack:** Python 3.14 (venv), pandas, ta, stdlib

## Global Constraints

- **Venv obbligatorio**: `../.venv/bin/python` (da src/).
- Contratto scraper `run(config) -> dict` con funzioni pure.
- Riusare `records_to_frame` da `scrapers.indicators` (no duplicazione).
- SMA50/SMA200 ricalcolate dai record cache (pattern indicators.py con `ta`).
- Isolamento per-ticker: ticker senza dati sufficienti → esclusi dal denominatore.
- **compute_signal NON cambia** — la breadth è conferma macro, non scoring ticker.
- **Il progetto NON è un repo git** → i passi "Commit" vanno saltati.
- Test suite: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`.

---

### Task 1: `pct_sma_scraper.py` — modulo + test

**Files:**
- Create: `src/scrapers/pct_sma_scraper.py`
- Create: `src/tests/test_pct_sma_scraper.py`

**Interfaces:**
- Consumes: `config["cache_path"]` (assoluto, risolto dall'orchestratore), `config["tickers"]`
- Produces:
  - `load_cache(cache_path: str) -> dict` (riusa pattern indicators)
  - `ticker_above_sma(records: list[dict], sma_fast, sma_slow) -> tuple[bool | None, bool | None]`
  - `aggregate(tickers: dict, cache: dict, sma_fast, sma_slow) -> dict`
  - `build_result(aggregated: dict, fetched_at: str | None = None) -> dict`
  - `run(config: dict | None = None) -> dict`

- [ ] **Step 1: Scrivi i test falliti in `src/tests/test_pct_sma_scraper.py`**

```python
"""Unit tests for the PCT SMA scraper (breadth, pure functions)."""

from __future__ import annotations

import json
import tempfile
import unittest
from typing import Any

from scrapers.pct_sma_scraper import aggregate, build_result, load_cache


def _records(n: int = 60, price: float = 100.0) -> list[dict[str, Any]]:
    """Records with constant price → above SMA50/200 (last close == sma)."""
    import pandas as pd
    return [
        {
            "date": pd.Timestamp(d).strftime("%Y-%m-%d"),
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": 1000,
        }
        for d in pd.date_range("2026-01-01", periods=n, freq="D")
    ]


def _rising_records(n: int = 60) -> list[dict[str, Any]]:
    """Records rising to 110 → above SMA50 (last close > sma50)."""
    import pandas as pd
    return [
        {
            "date": pd.Timestamp(d).strftime("%Y-%m-%d"),
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0 + i * 0.2,  # sale gradualmente
            "volume": 1000,
        }
        for i, d in enumerate(pd.date_range("2026-01-01", periods=n, freq="D"))
    ]


class TestLoadCache(unittest.TestCase):
    def test_loads_cache(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"semiconductors": {"AMAT": _records(5)}}, fh)
            path = fh.name
        cache = load_cache(path)
        self.assertIn("AMAT", cache["semiconductors"])

    def test_missing_cache_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_cache("/nonexistent/cache.json")


class TestAggregate(unittest.TestCase):
    def test_aggregates_per_category_and_total(self):
        tickers = {
            "semiconductors": [{"symbol": "AMAT", "name": "A"}],
            "defense": [{"symbol": "RTX", "name": "R"}],
        }
        cache = {
            "semiconductors": {"AMAT": _rising_records()},   # sopra SMA50
            "defense": {"RTX": _records()},                   # uguale a SMA50 (>= ok)
        }
        result = aggregate(tickers, cache)
        semi = result["semiconductors"]
        self.assertEqual(semi["total"], 1)
        self.assertEqual(semi["above_sma50"], 1)
        self.assertEqual(semi["pct_sma50"], 100.0)
        total = result["total"]
        self.assertEqual(total["total"], 2)
        self.assertEqual(total["above_sma50"], 2)
        self.assertEqual(total["pct_sma50"], 100.0)

    def test_ticker_with_insufficient_data_excluded(self):
        tickers = {"semiconductors": [{"symbol": "AMAT", "name": "A"}]}
        cache = {"semiconductors": {"AMAT": _records(5)}}  # < 50 record → escluso
        result = aggregate(tickers, cache)
        self.assertEqual(result["total"]["total"], 0)
        self.assertEqual(result["total"]["pct_sma50"], 0.0)


class TestBuildResult(unittest.TestCase):
    def test_builds_file_json_shape(self):
        agg = {
            "semiconductors": {"above_sma50": 1, "total": 1, "pct_sma50": 100.0,
                               "above_sma200": 1, "pct_sma200": 100.0},
            "total": {"above_sma50": 1, "total": 1, "pct_sma50": 100.0,
                      "above_sma200": 1, "pct_sma200": 100.0},
        }
        result = build_result(agg, fetched_at="2026-08-12T00:00:00+00:00")
        self.assertEqual(result["total"]["pct_sma50"], 100.0)
        self.assertEqual(result["frequency"], "daily")
        self.assertEqual(result["status"], "fresh")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Esegui i test per verificare che falliscano**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_pct_sma_scraper -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scrapers.pct_sma_scraper'`

- [ ] **Step 3: Implementa `src/scrapers/pct_sma_scraper.py`**

```python
"""Percentage above SMA scraper module (sector breadth).

Reads the OHLCV cache written by ``ohlcv_fetcher`` and computes the share of
tickers whose last close is above SMA50 and SMA200, per category and total.
This is the sector breadth used by the buy-the-dip strategy as a macro
confirmation (indicators #13-14): % above SMA50 < 20% = oversold market,
% above SMA200 < 30% = deteriorated market.

NOTE: the original source (IndexIndicators.com) exposes the chart as a PNG
image only — not scrapable. We compute the breadth locally from our own OHLCV
data (sector breadth, more aligned with the strategy's universe).

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ta.trend import SMAIndicator

from scrapers.indicators import records_to_frame

logger = logging.getLogger(__name__)

DEFAULT_SMA_FAST = 50
DEFAULT_SMA_SLOW = 200
DEFAULT_STALE_AFTER_HOURS = 24
FREQUENCY = "daily"


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def load_cache(cache_path: str) -> dict[str, Any]:
    """Load the OHLCV cache JSON from disk.

    Raises:
        FileNotFoundError: If the cache file does not exist.
    """
    path = Path(cache_path)
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def ticker_above_sma(
    records: list[dict[str, Any]],
    sma_fast: int = DEFAULT_SMA_FAST,
    sma_slow: int = DEFAULT_SMA_SLOW,
) -> tuple[bool | None, bool | None]:
    """Return (above_sma50, above_sma200) for a ticker's OHLCV records.

    Returns None for a SMA if there is not enough data or the last value is
    missing (ticker excluded from that denominator).
    """
    if len(records) < max(sma_fast, sma_slow):
        return None, None
    try:
        frame = records_to_frame(records)
    except Exception as error:  # noqa: BLE001 - per-ticker isolation
        logger.warning("pct_sma: frame conversion failed: %s", error)
        return None, None
    close = frame["Close"]
    last_close = float(close.iloc[-1])

    def _above(window: int) -> bool | None:
        series = SMAIndicator(close=close, window=window).sma_indicator()
        last_sma = series.iloc[-1]
        if last_sma is None or _is_nan(last_sma):
            return None
        return last_close >= float(last_sma)

    return _above(sma_fast), _above(sma_slow)


def _is_nan(value: Any) -> bool:
    """NaN check without importing pandas at call sites."""
    try:
        import math
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return True


def aggregate(
    tickers: dict[str, Any],
    cache: dict[str, Any],
    sma_fast: int = DEFAULT_SMA_FAST,
    sma_slow: int = DEFAULT_SMA_SLOW,
) -> dict[str, dict[str, Any]]:
    """Compute above-SMA counts per category and total.

    Tickers without enough data are excluded from the denominator. Returns
    dict with per-category entries plus a "total" key.
    """
    categories: dict[str, dict[str, Any]] = {}

    def _init() -> dict[str, Any]:
        return {
            "above_sma50": 0,
            "total": 0,
            "pct_sma50": 0.0,
            "above_sma200": 0,
            "pct_sma200": 0.0,
        }

    total_stats = _init()

    for category, entries in tickers.items():
        stats = _init()
        for entry in entries:
            symbol = entry["symbol"]
            records = cache.get(category, {}).get(symbol, [])
            above_fast, above_slow = ticker_above_sma(records, sma_fast, sma_slow)
            if above_fast is None and above_slow is None:
                continue  # dati insufficienti → escluso
            stats["total"] += 1
            total_stats["total"] += 1
            if above_fast is True:
                stats["above_sma50"] += 1
                total_stats["above_sma50"] += 1
            if above_slow is True:
                stats["above_sma200"] += 1
                total_stats["above_sma200"] += 1
        if stats["total"] > 0:
            stats["pct_sma50"] = round(stats["above_sma50"] / stats["total"] * 100, 1)
            stats["pct_sma200"] = round(stats["above_sma200"] / stats["total"] * 100, 1)
        categories[category] = stats

    if total_stats["total"] > 0:
        total_stats["pct_sma50"] = round(total_stats["above_sma50"] / total_stats["total"] * 100, 1)
        total_stats["pct_sma200"] = round(total_stats["above_sma200"] / total_stats["total"] * 100, 1)
    categories["total"] = total_stats
    return categories


def build_result(
    aggregated: dict[str, dict[str, Any]],
    fetched_at: str | None = None,
    stale_after_hours: int = DEFAULT_STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Build the output dict in the file.json format."""
    result: dict[str, Any] = {key: dict(value) for key, value in aggregated.items()}
    result["fetched_at"] = fetched_at or _now_iso()
    result["frequency"] = FREQUENCY
    result["stale_after_hours"] = stale_after_hours
    result["status"] = "fresh"
    return result


def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute the sector breadth from the OHLCV cache.

    Args:
        config: Overrides + injected ``tickers`` and ``cache_path``.
    """
    config = config or {}
    tickers = config.get("tickers", {})
    cache_path = config.get("cache_path")
    if not cache_path:
        raise ValueError("pct_sma requires 'cache_path' in config")

    cache = load_cache(cache_path)
    sma_fast = config.get("sma_fast", DEFAULT_SMA_FAST)
    sma_slow = config.get("sma_slow", DEFAULT_SMA_SLOW)
    aggregated = aggregate(tickers, cache, sma_fast=sma_fast, sma_slow=sma_slow)
    return build_result(
        aggregated,
        stale_after_hours=config.get("stale_after_hours", DEFAULT_STALE_AFTER_HOURS),
    )
```

- [ ] **Step 4: Esegui i test per verificare che passino**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_pct_sma_scraper -v`
Expected: PASS (5 test)

- [ ] **Step 5: (Niente commit — progetto non è un repo git)**

---

### Task 2: Ampliamento tickers + Config.yaml

**Files:**
- Modify: `config.yaml`

**Interfaces:**
- Consumes: niente
- Produces: universo ~29 ticker + sezione `pct_sma`

- [ ] **Step 1: Amplia la sezione `tickers` in config.yaml**

Sotto `semiconductors`, aggiungi dopo ENTG:
```yaml
    - symbol: NVDA
      name: NVIDIA
    - symbol: INTC
      name: Intel
    - symbol: TXN
      name: Texas Instruments
    - symbol: SWKS
      name: Skyworks Solutions
    - symbol: MPWR
      name: Monolithic Power Systems
    - symbol: ON
      name: ON Semiconductor
    - symbol: NXPI
      name: NXP Semiconductors
```

Sotto `defense`, aggiungi dopo LHX:
```yaml
    - symbol: AXON
      name: Axon Enterprise
    - symbol: HWM
      name: Howmet Aerospace
    - symbol: HEI
      name: HEICO
    - symbol: TDG
      name: TransDigm Group
    - symbol: TXT
      name: Textron
```

- [ ] **Step 2: Aggiungi la sezione `pct_sma` in config.yaml** (dopo indicators, prima di tickers)

```yaml
  pct_sma:
    module: scrapers.pct_sma_scraper
    output_key: pct_sma
    schedule: daily
    config:
      cache_path: output/ohlcv_cache.json
      sma_fast: 50
      sma_slow: 200
      stale_after_hours: 24
```

- [ ] **Step 3: Verifica che la config valida**

Run: `cd src && ../.venv/bin/python -c "from config_loader import load_config; c = load_config('../config.yaml'); print(len(c['tickers']['semiconductors']), len(c['tickers']['defense'])); print(list(c['scrapers'].keys()))"`
Expected: `19 10` e `['fgi', 'aaii', 'vix', 'pcr', 'ohlcv', 'indicators', 'pct_sma']`

- [ ] **Step 4: Esegui la suite**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS (test esistenti + pct_sma)

- [ ] **Step 5: (Niente commit — progetto non è un repo git)**

---

### Task 3: Report HTML — card breadth + legenda

**Files:**
- Modify: `src/report_html.py`
- Modify: `src/tests/test_report_html.py`

**Interfaces:**
- Consumes: `pct_sma` dict dal Task 1-2
- Produces: card "Breadth settoriale" con semaforo, voce legenda

- [ ] **Step 1: Aggiungi la card breadth in `render_market_cards`** (dopo card PCR)

```python
    pct_sma = data.get("pct_sma", {})
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
        '<div class="card"><div class="label">Breadth settoriale</div>'
        f'<div class="value">SMA50 {fmt(p50)}% {_breadth_sema(p50, 20, 50)}</div>'
        f'<div class="meta">SMA200 {fmt(p200)}% {_breadth_sema(p200, 30, 60)}</div>'
        f'<div class="meta">Aggiornato: {format_iso_dt(pct_sma.get("fetched_at"))}</div></div>'
    )
```

- [ ] **Step 2: Aggiungi la voce breadth in `_LEGEND_MARKET`**

```python
    {
        "name": "Breadth settoriale (% sopra SMA)",
        "range": "%",
        "short": "Quota di ticker dei settori sopra SMA50/SMA200.",
        "detail": (
            "Percentuale di ticker (semiconduttori+difesa) con prezzo sopra la media "
            "mobile a 50 e 200 giorni. Sotto il 20% su SMA50 il settore è ipervenduto "
            "diffuso (potenziale opportunità); sotto il 30% su SMA200 il mercato è "
            "deteriorato. Sopra il 50%/60% la struttura è positiva. Calcolata "
            "localmente dai dati OHLCV (IndexIndicators non è scrapabile)."
        ),
    },
```

- [ ] **Step 3: Aggiungi test report_html per breadth**

```python
    def test_market_cards_contains_breadth(self):
        data = _sample_data()
        data["pct_sma"] = {"total": {"pct_sma50": 69.0, "pct_sma200": 86.2,
                                     "fetched_at": "2026-08-12T00:00:00+00:00"}}
        html = render_market_cards(data)
        self.assertIn("Breadth settoriale", html)
        self.assertIn("69", html)

    def test_breadth_legend_entry(self):
        html = render_legend()
        self.assertIn("Breadth settoriale", html)
        self.assertIn("ipervenduto", html)
```

- [ ] **Step 4: Esegui la suite completa**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 5: (Niente commit — progetto non è un repo git)**

---

### Task 4: Documentazione — README + context

**Files:**
- Modify: `README.md`
- Modify: `.opencode/context/project-intelligence/scraping-patterns.md`
- Modify: `.opencode/context/project-intelligence/technical-domain.md`
- Modify: `.opencode/context/project-intelligence/navigation.md`

**Interfaces:**
- Consumes: niente
- Produces: documentazione del modulo

- [ ] **Step 1: Aggiorna README.md** — tabella "Dove sono gli scraper" e "Stato dei moduli"

```markdown
| `pct_sma_scraper.py` | — (calcolo locale OHLCV) | % sopra SMA50/SMA200 per settore | giornaliera |
```
```markdown
| `pct_sma_scraper.py` | ✅ Funzionante | Breadth settoriale da OHLCV locale (IndexIndicators: solo PNG, non scrapabile) |
```
E Roadmap: spunta `pct_sma_scraper`.

- [ ] **Step 2: Aggiorna scraping-patterns.md** — sezione "PCT SMA: breadth da OHLCV locale"

```markdown
## PCT SMA: breadth settoriale da OHLCV locale (non IndexIndicators!)
IndexIndicators espone solo PNG del grafico (non parsabile). Calcolare la
percentuale di ticker sopra SMA50/SMA200 dai dati OHLCV della cache locale.
Riusare `records_to_frame` da indicators.py + `ta.trend.SMAIndicator`.
```

- [ ] **Step 3: Aggiorna technical-domain.md** — Codebase References

```markdown
**Scraper PCT SMA**: `src/scrapers/pct_sma_scraper.py` — breadth settoriale % sopra SMA50/200 da OHLCV locale
```

- [ ] **Step 4: Aggiorna navigation.md** — log

```markdown
- **2026-08-12**: pct_sma_scraper.py (breadth da OHLCV locale) — scraping-patterns.md v1.3, technical-domain.md v1.7, navigation.md v1.5
```

- [ ] **Step 5: Esegui la suite completa**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 6: (Niente commit — progetto non è un repo git)**
