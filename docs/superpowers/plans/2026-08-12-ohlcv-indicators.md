# OHLCV + Indicators Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementare `ohlcv_fetcher.py` (fetch OHLCV da Yahoo via yfinance → cache su disco) e `indicators.py` (calcolo RSI/OBV/MFI/SMA/drawdown con libreria `ta`), più iniezione `tickers` nell'orchestratore e setup venv.

**Architecture:** Estensione del pattern scraper esistente. `ohlcv_fetcher` scarica OHLCV per ogni ticker della sezione `tickers:` (iniettata dall'orchestratore), serializza in cache JSON su disco, ritorna dict compatti. `indicators` legge la cache, calcola gli indicatori con `ta`, ritorna dict nel formato file.json. Entrambi `run(config) -> dict`.

**Tech Stack:** Python 3.14 (venv), yfinance 1.5.2, pandas 3.0.5, ta 0.11.0, requests/pyyaml/bs4 (esistenti)

## Global Constraints

- **Venv obbligatorio**: Python di sistema è Arch/PEP 668 (externally-managed). Tutto il lavoro pip avviene in `.venv/` del progetto. I test si eseguono con `.venv/bin/python`.
- **pandas-ta ESCLUSO**: numba non supporta Python 3.14. Usare `ta` 0.11.0.
- Sezione `tickers` opzionale — i moduli funzionano anche senza (ritornano status senza ticker).
- Contratto scraper: `run(config: dict) -> dict` con funzioni pure + DI per la rete.
- Type hints su tutte le funzioni, snake_case, errori `ValueError` descrittivi.
- Isolamento per-ticker: un ticker che fallisce non blocca gli altri (errore nel campo `error` del ticker).
- **Il progetto NON è un repo git** → i passi "Commit" vanno saltati o sostituiti con nota.
- Test suite completa: `.venv/bin/python -m unittest discover -s tests -v` dalla cartella `src/`.
- Il consolidator NON va modificato (stale_summary per modulo via campo `status` top-level).

---

### Task 1: Setup venv + dipendenze

**Files:**
- Create: `.venv/` (virtualenv del progetto)
- Modify: `.gitignore` (aggiungere `.venv/`)

**Interfaces:**
- Consumes: niente
- Produces: `.venv/bin/python` con yfinance 1.5.2, pandas 3.0.5, ta 0.11.0, pyyaml, requests, bs4

- [ ] **Step 1: Crea il venv e installa le dipendenze**

```bash
cd /home/fibbione/Progetti/scraper-system
python -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install yfinance==1.5.2 pandas==3.0.5 ta==0.11.0
.venv/bin/pip install pyyaml requests beautifulsoup4   # già presenti a sistema, servono anche nel venv per i test
```

- [ ] **Step 2: Verifica le installazioni**

```bash
.venv/bin/python -c "import yfinance, pandas, ta; print('yfinance', yfinance.__version__); print('pandas', pandas.__version__); print('ta', ta.__version__)"
```
Expected: `yfinance 1.5.2`, `pandas 3.0.5`, `ta 0.11.0` (o versioni compatibili)

- [ ] **Step 3: Aggiungi `.venv/` al `.gitignore`**

Apri `.gitignore` e aggiungi:
```
.venv/
```

- [ ] **Step 4: Verifica che i test esistenti passano col venv**

```bash
cd /home/fibbione/Progetti/scraper-system/src && ../.venv/bin/python -m unittest discover -s tests -v
```
Expected: PASS (43 test esistenti)

- [ ] **Step 5: (Niente commit — progetto non è un repo git)**

---

### Task 2: Iniezione `tickers` + risoluzione `cache_path` nell'orchestratore

**Files:**
- Modify: `src/orchestrator.py`

**Interfaces:**
- Consumes: `load_config(config_path)` esistente
- Produces: `_run_scraper_safely(name, scraper, base_dir, tickers)` — passa a ogni scraper un config arricchito con `tickers` (top-level) e `cache_path` risolto assoluto

- [ ] **Step 1: Scrivi il test fallito in `src/tests/test_orchestrator.py`** (aggiungi al file esistente, classe TestOrchestrator)

```python
    def test_run_injects_tickers_to_scraper_config(self):
        received = {}

        module = types.ModuleType("tests.mock_ticker_scraper")

        def run(config):
            received["tickers"] = config.get("tickers")
            return {"status": "fresh"}

        module.run = run
        sys.modules["tests.mock_ticker_scraper"] = module
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/config.yaml"
            output_path = f"{tmp}/output.json"
            db_path = f"{tmp}/audit.db"
            with open(config_path, "w", encoding="utf-8") as fh:
                fh.write(
                    "scrapers:\n"
                    "  mock:\n"
                    "    module: tests.mock_ticker_scraper\n"
                    "    output_key: mock\n"
                    "    schedule: daily\n"
                    "tickers:\n"
                    "  semiconductors:\n"
                    "    - symbol: AMAT\n"
                    "      name: Applied Materials\n"
                )
            run(config_path, output_path, db_path)
        self.assertEqual(
            received["tickers"]["semiconductors"][0]["symbol"], "AMAT"
        )
```

- [ ] **Step 2: Esegui il test per verificare che fallisca**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_orchestrator.TestOrchestrator.test_run_injects_tickers_to_scraper_config -v`
Expected: FAIL — `received["tickers"]` è `None` (o chiave assente)

- [ ] **Step 3: Implementa l'iniezione in `src/orchestrator.py`**

Modifica `_run_scraper_safely` per accettare il config arricchito e `run()` per costruirlo:

```python
def _run_scraper_safely(
    name: str,
    scraper: dict[str, Any],
    base_dir: Path,
    tickers: dict[str, Any],
) -> tuple[dict[str, Any] | None, str, str | None]:
    """Run one scraper, returning (result, status, error).

    Injects the top-level ``tickers`` section and resolves ``cache_path``
    (relative to the project root) into the scraper config.
    """
    scraper_config = dict(scraper.get("config", {}))
    scraper_config["tickers"] = tickers
    if "cache_path" in scraper_config:
        scraper_config["cache_path"] = str(base_dir / scraper_config["cache_path"])
    try:
        run = get_scraper(scraper["module"])
        result = run(scraper_config)
        return result, "success", None
    except Exception as error:  # noqa: BLE001 - isolate per-module failures
        logger.error("Scraper %s failed: %s", name, error)
        return None, "error", str(error)
```

E nel loop di `run()`, sostituisci la chiamata:

```python
        for name, scraper in config["scrapers"].items():
            result, status, error = _run_scraper_safely(
                name, scraper, base_dir, config.get("tickers", {})
            )
```

- [ ] **Step 4: Esegui i test per verificare che passino**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS (44 test — 43 esistenti + 1 nuovo)

- [ ] **Step 5: (Niente commit — progetto non è un repo git)**

---

### Task 3: `ohlcv_fetcher.py` — fetch OHLCV da Yahoo → cache su disco

**Files:**
- Create: `src/scrapers/ohlcv_fetcher.py`
- Create: `src/tests/test_ohlcv_fetcher.py`

**Interfaces:**
- Consumes: `config["tickers"]` (iniettato da orchestrator), `config["cache_path"]` (assoluto, risolto da orchestrator)
- Produces:
  - `fetch_ohlcv(symbol, period="1y", interval="1d", timeout=10) -> pd.DataFrame` (DI: `yf.download` mockabile)
  - `frame_to_records(df: pd.DataFrame) -> list[dict[str, Any]]`
  - `serialize_cache(cache: dict[str, dict[str, list[dict]]]) -> str`
  - `build_result(tickers, cache) -> dict` (output formato file.json)
  - `run(config: dict) -> dict`

- [ ] **Step 1: Scrivi i test falliti in `src/tests/test_ohlcv_fetcher.py`**

```python
"""Unit tests for the OHLCV fetcher scraper (pure functions, no network)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from scrapers.ohlcv_fetcher import (
    build_result,
    frame_to_records,
    serialize_cache,
)


def _sample_frame() -> pd.DataFrame:
    index = pd.to_datetime(["2026-08-07", "2026-08-08"])
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.5, 102.5],
            "Volume": [1000, 1100],
        },
        index=index,
    )


class TestFrameToRecords(unittest.TestCase):
    def test_converts_frame_to_records(self):
        records = frame_to_records(_sample_frame())
        self.assertEqual(len(records), 2)
        first = records[0]
        self.assertEqual(first["date"], "2026-08-07")
        self.assertEqual(first["open"], 100.0)
        self.assertEqual(first["high"], 102.0)
        self.assertEqual(first["low"], 99.0)
        self.assertEqual(first["close"], 101.5)
        self.assertEqual(first["volume"], 1000)


class TestSerializeCache(unittest.TestCase):
    def test_serializes_nested_cache(self):
        cache = {
            "semiconductors": {
                "AMAT": [{"date": "2026-08-07", "close": 101.5}]
            }
        }
        text = serialize_cache(cache)
        self.assertIn('"AMAT"', text)
        self.assertIn("2026-08-07", text)


class TestBuildResult(unittest.TestCase):
    def test_builds_output_shape(self):
        tickers = {"semiconductors": [{"symbol": "AMAT", "name": "Applied Materials"}]}
        cache = {
            "semiconductors": {
                "AMAT": [{"date": "2026-08-07", "close": 101.5}]
            }
        }
        result = build_result(tickers, cache, fetched_at="2026-08-08T00:00:00+00:00")
        amat = result["semiconductors"]["AMAT"]
        self.assertEqual(amat["symbol"], "AMAT")
        self.assertEqual(amat["last_close"], 101.5)
        self.assertEqual(amat["last_date"], "2026-08-07")
        self.assertEqual(result["status"], "fresh")

    def test_error_ticker_is_skipped(self):
        tickers = {"semiconductors": [{"symbol": "AMAT", "name": "A"}]}
        cache = {"semiconductors": {}}
        result = build_result(tickers, cache)
        self.assertNotIn("AMAT", result["semiconductors"])
        self.assertEqual(result["status"], "stale")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Esegui i test per verificare che falliscano**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_ohlcv_fetcher -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scrapers.ohlcv_fetcher'`

- [ ] **Step 3: Implementa `src/scrapers/ohlcv_fetcher.py`**

```python
"""OHLCV fetcher scraper module.

Fetches daily OHLCV data from Yahoo Finance (via yfinance) for every ticker in
the config ``tickers`` section, serializes it to a JSON cache on disk, and
returns a compact per-ticker summary in the file.json output format.

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

DEFAULT_PERIOD = "1y"
DEFAULT_INTERVAL = "1d"
DEFAULT_TIMEOUT = 10
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 2.0
DEFAULT_STALE_AFTER_HOURS = 24
FREQUENCY = "daily"


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def fetch_ohlcv(
    symbol: str,
    period: str = DEFAULT_PERIOD,
    interval: str = DEFAULT_INTERVAL,
    timeout: int = DEFAULT_TIMEOUT,
) -> pd.DataFrame:
    """Download OHLCV data for a single symbol via yfinance."""
    df = yf.download(
        symbol,
        period=period,
        interval=interval,
        progress=False,
        auto_adjust=True,
        timeout=timeout,
    )
    if df is None or df.empty:
        raise ValueError(f"No OHLCV data returned for {symbol}")
    return df


def frame_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a yfinance DataFrame to a list of plain dict records.

    Each record: {date, open, high, low, close, volume}. Dates are ISO strings.
    """
    records: list[dict[str, Any]] = []
    for date, row in df.iterrows():
        records.append(
            {
                "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            }
        )
    return records


def serialize_cache(cache: dict[str, dict[str, list[dict[str, Any]]]]) -> str:
    """Serialize the OHLCV cache to a JSON string."""
    return json.dumps(cache, indent=2)


def _fetch_ticker_with_retry(
    symbol: str,
    period: str,
    interval: str,
    timeout: int,
    retries: int,
    backoff: float,
) -> pd.DataFrame:
    """Fetch one ticker's OHLCV with retry and exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return fetch_ohlcv(symbol, period=period, interval=interval, timeout=timeout)
        except Exception as error:  # noqa: BLE001 - yfinance raises mixed types
            last_error = error
            logger.warning(
                "OHLCV fetch %s attempt %d/%d failed: %s",
                symbol, attempt + 1, retries, error,
            )
            if attempt < retries - 1:
                time.sleep(backoff * (2**attempt))
    raise RuntimeError(f"OHLCV fetch failed after {retries} attempts: {last_error}")


def _fetch_all(tickers: dict[str, Any], config: dict[str, Any]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Fetch OHLCV for all tickers, grouped by category. Failures per-ticker."""
    period = config.get("period", DEFAULT_PERIOD)
    interval = config.get("interval", DEFAULT_INTERVAL)
    timeout = config.get("timeout", DEFAULT_TIMEOUT)
    retries = config.get("retries", DEFAULT_RETRIES)
    backoff = config.get("backoff", DEFAULT_BACKOFF)

    cache: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for category, entries in tickers.items():
        cache[category] = {}
        for entry in entries:
            symbol = entry["symbol"]
            try:
                df = _fetch_ticker_with_retry(symbol, period, interval, timeout, retries, backoff)
                cache[category][symbol] = frame_to_records(df)
            except Exception as error:  # noqa: BLE001 - per-ticker isolation
                logger.error("OHLCV fetch failed for %s: %s", symbol, error)
    return cache


def build_result(
    tickers: dict[str, Any],
    cache: dict[str, dict[str, list[dict[str, Any]]]],
    fetched_at: str | None = None,
    stale_after_hours: int = DEFAULT_STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Build the output dict in the file.json format.

    One entry per ticker with OHLCV data; tickers without data are omitted.
    The module-level ``status`` is 'fresh' iff every configured ticker has data.
    """
    fetched_at = fetched_at or _now_iso()
    result: dict[str, Any] = {}
    total = 0
    ok = 0

    for category, entries in tickers.items():
        result[category] = {}
        for entry in entries:
            symbol = entry["symbol"]
            records = cache.get(category, {}).get(symbol, [])
            total += 1
            if not records:
                continue
            ok += 1
            result[category][symbol] = {
                "symbol": symbol,
                "name": entry["name"],
                "last_close": records[-1]["close"],
                "last_date": records[-1]["date"],
                "fetched_at": fetched_at,
                "frequency": FREQUENCY,
                "stale_after_hours": stale_after_hours,
                "status": "fresh",
            }

    result["status"] = "fresh" if total > 0 and ok == total else "stale"
    return result


def _save_cache(cache_path: str, cache: dict[str, dict[str, list[dict[str, Any]]]]) -> None:
    """Write the OHLCV cache to disk (creates parent dirs)."""
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_cache(cache), encoding="utf-8")


def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch OHLCV for all configured tickers and save to cache.

    Args:
        config: Overrides + injected ``tickers`` and ``cache_path``.
    """
    config = config or {}
    tickers = config.get("tickers", {})
    cache_path = config.get("cache_path")

    cache = _fetch_all(tickers, config)
    if cache_path:
        _save_cache(cache_path, cache)

    return build_result(
        tickers,
        cache,
        stale_after_hours=config.get("stale_after_hours", DEFAULT_STALE_AFTER_HOURS),
    )
```

- [ ] **Step 4: Esegui i test per verificare che passino**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_ohlcv_fetcher -v`
Expected: PASS (6 test)

- [ ] **Step 5: (Niente commit — progetto non è un repo git)**

---

### Task 4: `indicators.py` — calcolo indicatori con libreria `ta`

**Files:**
- Create: `src/scrapers/indicators.py`
- Create: `src/tests/test_indicators.py`

**Interfaces:**
- Consumes: `config["tickers"]`, `config["cache_path"]` (assoluto), `config["cache_path"]` letto da disco
- Produces:
  - `load_cache(cache_path: str) -> dict` (funzione pura con path iniettato)
  - `records_to_frame(records: list[dict]) -> pd.DataFrame`
  - `compute_indicators(frame: pd.DataFrame, rsi_window, mfi_window, sma_fast, sma_slow, drawdown_window) -> dict`
  - `build_result(tickers, indicators_by_ticker) -> dict`
  - `run(config: dict) -> dict`

- [ ] **Step 1: Scrivi i test falliti in `src/tests/test_indicators.py`**

```python
"""Unit tests for the indicators scraper (pure functions, no network)."""

from __future__ import annotations

import json
import tempfile
import unittest
from typing import Any

import pandas as pd

from scrapers.indicators import (
    build_result,
    compute_indicators,
    load_cache,
    records_to_frame,
)


def _constant_frame(n: int = 60, price: float = 100.0) -> pd.DataFrame:
    """A frame with constant close price → RSI/SMA are well-defined."""
    index = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "Open": [price] * n,
            "High": [price] * n,
            "Low": [price] * n,
            "Close": [price] * n,
            "Volume": [1000] * n,
        },
        index=index,
    )


def _records(n: int = 60, price: float = 100.0) -> list[dict[str, Any]]:
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


class TestRecordsToFrame(unittest.TestCase):
    def test_converts_records_to_frame(self):
        frame = records_to_frame(_records(5))
        self.assertEqual(len(frame), 5)
        self.assertEqual(frame["Close"].iloc[-1], 100.0)


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


class TestComputeIndicators(unittest.TestCase):
    def test_constant_price_gives_known_values(self):
        frame = _constant_frame()
        ind = compute_indicators(frame)
        # SMA of constant series equals the price
        self.assertAlmostEqual(ind["sma_50"], 100.0, places=4)
        self.assertAlmostEqual(ind["sma_200"], 100.0, places=4)  # NaN if < 200 rows
        self.assertIn("rsi_14", ind)
        self.assertIn("obv", ind)
        self.assertIn("mfi_14", ind)
        self.assertIn("drawdown_52w", ind)


class TestBuildResult(unittest.TestCase):
    def test_builds_output_shape(self):
        tickers = {"semiconductors": [{"symbol": "AMAT", "name": "A"}]}
        indicators = {"AMAT": {"rsi_14": 50.0, "obv": 100, "mfi_14": 50.0,
                               "sma_50": 100.0, "sma_200": None,
                               "drawdown_52w": 0.0}}
        result = build_result(tickers, indicators, fetched_at="2026-08-08T00:00:00+00:00")
        amat = result["semiconductors"]["AMAT"]
        self.assertEqual(amat["rsi_14"], 50.0)
        self.assertEqual(amat["status"], "fresh")
        self.assertEqual(result["status"], "fresh")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Esegui i test per verificare che falliscano**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_indicators -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scrapers.indicators'`

- [ ] **Step 3: Implementa `src/scrapers/indicators.py`**

```python
"""Technical indicators scraper module.

Reads the OHLCV cache written by ``ohlcv_fetcher`` and computes technical
indicators (RSI, OBV, MFI, SMA50, SMA200, drawdown 52w) using the ``ta``
library. Returns a dict in the file.json output format.

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
from ta.volume import (
    OnBalanceVolumeIndicator,
    money_flow_index,
)

logger = logging.getLogger(__name__)

DEFAULT_RSI_WINDOW = 14
DEFAULT_MFI_WINDOW = 14
DEFAULT_SMA_FAST = 50
DEFAULT_SMA_SLOW = 200
DEFAULT_DRAWDOWN_WINDOW = 252
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


def records_to_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert a list of OHLCV record dicts to a pandas DataFrame."""
    frame = pd.DataFrame(records)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date").sort_index()
    return frame


def compute_indicators(
    frame: pd.DataFrame,
    rsi_window: int = DEFAULT_RSI_WINDOW,
    mfi_window: int = DEFAULT_MFI_WINDOW,
    sma_fast: int = DEFAULT_SMA_FAST,
    sma_slow: int = DEFAULT_SMA_SLOW,
    drawdown_window: int = DEFAULT_DRAWDOWN_WINDOW,
) -> dict[str, Any]:
    """Compute technical indicators from an OHLCV DataFrame.

    Returns the latest values: rsi_14, obv, mfi_14, sma_50, sma_200,
    drawdown_52w. Missing values (insufficient data) are None.
    """
    close = frame["Close"]
    high = frame["High"]
    low = frame["Low"]
    volume = frame["Volume"]

    rsi_series = RSIIndicator(close=close, window=rsi_window).rsi()
    sma_fast_series = SMAIndicator(close=close, window=sma_fast).sma_indicator()
    sma_slow_series = SMAIndicator(close=close, window=sma_slow).sma_indicator()
    obv_series = OnBalanceVolumeIndicator(close=close, volume=volume).on_balance_volume()
    mfi_series = money_flow_index(high, low, close, volume, window=mfi_window)

    rolling_max = close.rolling(window=drawdown_window, min_periods=1).max()
    drawdown = (close - rolling_max) / rolling_max * 100.0

    def _last(series: pd.Series) -> float | None:
        value = series.iloc[-1]
        if pd.isna(value):
            return None
        return round(float(value), 4)

    return {
        "rsi_14": _last(rsi_series),
        "obv": _last(obv_series),
        "mfi_14": _last(mfi_series),
        "sma_50": _last(sma_fast_series),
        "sma_200": _last(sma_slow_series),
        "drawdown_52w": _last(drawdown),
    }


def build_result(
    tickers: dict[str, Any],
    indicators_by_ticker: dict[str, dict[str, Any]],
    fetched_at: str | None = None,
    stale_after_hours: int = DEFAULT_STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Build the output dict in the file.json format.

    One entry per ticker with indicators; tickers without indicators are
    omitted. The module-level ``status`` is 'fresh' iff every configured
    ticker has indicators.
    """
    fetched_at = fetched_at or _now_iso()
    result: dict[str, Any] = {}
    total = 0
    ok = 0

    for category, entries in tickers.items():
        result[category] = {}
        for entry in entries:
            symbol = entry["symbol"]
            total += 1
            ind = indicators_by_ticker.get(symbol)
            if not ind:
                continue
            ok += 1
            entry_result = dict(ind)
            entry_result.update(
                {
                    "symbol": symbol,
                    "name": entry["name"],
                    "fetched_at": fetched_at,
                    "frequency": FREQUENCY,
                    "stale_after_hours": stale_after_hours,
                    "status": "fresh",
                }
            )
            result[category][symbol] = entry_result

    result["status"] = "fresh" if total > 0 and ok == total else "stale"
    return result


def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute indicators from the OHLCV cache.

    Args:
        config: Overrides + injected ``tickers`` and ``cache_path``.
    """
    config = config or {}
    tickers = config.get("tickers", {})
    cache_path = config.get("cache_path")
    if not cache_path:
        raise ValueError("indicators requires 'cache_path' in config")

    cache = load_cache(cache_path)
    rsi_window = config.get("rsi_window", DEFAULT_RSI_WINDOW)
    mfi_window = config.get("mfi_window", DEFAULT_MFI_WINDOW)
    sma_fast = config.get("sma_fast", DEFAULT_SMA_FAST)
    sma_slow = config.get("sma_slow", DEFAULT_SMA_SLOW)
    drawdown_window = config.get("drawdown_window", DEFAULT_DRAWDOWN_WINDOW)

    indicators_by_ticker: dict[str, dict[str, Any]] = {}
    for category, entries in tickers.items():
        for entry in entries:
            symbol = entry["symbol"]
            records = cache.get(category, {}).get(symbol, [])
            if not records:
                continue
            try:
                frame = records_to_frame(records)
                indicators_by_ticker[symbol] = compute_indicators(
                    frame,
                    rsi_window=rsi_window,
                    mfi_window=mfi_window,
                    sma_fast=sma_fast,
                    sma_slow=sma_slow,
                    drawdown_window=drawdown_window,
                )
            except Exception as error:  # noqa: BLE001 - per-ticker isolation
                logger.error("Indicator computation failed for %s: %s", symbol, error)

    return build_result(
        tickers,
        indicators_by_ticker,
        stale_after_hours=config.get("stale_after_hours", DEFAULT_STALE_AFTER_HOURS),
    )
```

- [ ] **Step 4: Esegui i test per verificare che passino**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_indicators -v`
Expected: PASS (5 test)

- [ ] **Step 5: (Niente commit — progetto non è un repo git)**

---

### Task 5: Config.yaml — registra i moduli ohlcv e indicators

**Files:**
- Modify: `config.yaml`

**Interfaces:**
- Consumes: niente
- Produces: sezione `scrapers:` con `ohlcv` e `indicators` come da design

- [ ] **Step 1: Aggiungi i due scraper in `config.yaml`** (dopo `vix:`, prima di `tickers:`)

```yaml
  ohlcv:
    module: scrapers.ohlcv_fetcher
    output_key: ohlcv
    schedule: daily
    config:
      cache_path: output/ohlcv_cache.json
      period: 1y
      interval: 1d
      timeout: 20
      retries: 3
      backoff: 2.0
      stale_after_hours: 24

  indicators:
    module: scrapers.indicators
    output_key: indicators
    schedule: daily
    config:
      cache_path: output/ohlcv_cache.json
      rsi_window: 14
      mfi_window: 14
      sma_fast: 50
      sma_slow: 200
      drawdown_window: 252
      stale_after_hours: 24
```

- [ ] **Step 2: Verifica che la config valida**

Run: `cd src && ../.venv/bin/python -c "from config_loader import load_config; c = load_config('../config.yaml'); print(list(c['scrapers'].keys()))"`
Expected: `['fgi', 'aaii', 'vix', 'ohlcv', 'indicators']`

- [ ] **Step 3: Esegui tutti i test**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS (54 test — 44 + 6 ohlcv + 5 indicators, arrotondato al reale)

- [ ] **Step 4: (Niente commit — progetto non è un repo git)**

---

### Task 6: Documentazione — README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: niente
- Produces: README aggiornato con i nuovi moduli

- [ ] **Step 1: Aggiorna la tabella "Dove sono gli scraper"**

Sposta `ohlcv_fetcher.py` e `indicators.py` dalla riga "(da creare)" alla lista funzionante:
```markdown
| `ohlcv_fetcher.py` | Yahoo (yfinance) | OHLCV per ticker (cache) | giornaliera |
| `indicators.py` | — | RSI, OBV, MFI, SMA50/200, drawdown | giornaliera |
```

- [ ] **Step 2: Aggiorna la tabella "Stato dei moduli"**

```markdown
| `ohlcv_fetcher.py` | ✅ Funzionante | OHLCV da Yahoo via yfinance, cache su disco (output/ohlcv_cache.json) |
| `indicators.py` | ✅ Funzionante | RSI/OBV/MFI/SMA50/200/drawdown con libreria ta (pandas-ta escluso: numba incompatibile Python 3.14) |
| PCR / SMA / Insider | ⏳ Da creare | — |
```

- [ ] **Step 3: Aggiorna la Roadmap**

```markdown
- [ ] Creare i moduli PCR, SMA, Insider
- [x] Creare `ohlcv_fetcher.py` (yfinance) e `indicators.py` (ta)
- [ ] Integrare uno scheduler (cron / `schedule` Python) per esecuzione giornaliera/settimanale
- [ ] Aggiungere fallback per fonti instabili (es. FGI)
```

- [ ] **Step 4: (Niente commit — progetto non è un repo git)**
