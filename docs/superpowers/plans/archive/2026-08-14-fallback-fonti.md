# Fallback Fonti Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Creare un helper generico per fallback fonti (`src/fetch_utils.py`) e applicarlo a FGI (catena CNN → feargreedmeter → feargreedindex) e AAII (consolidamento fallback interno).

**Architecture:** `fetch_utils.py` espone `fetch_first_success` (prova più fonti in sequenza) e `try_parsers` (prova più parser sullo stesso body). FGI usa entrambi: fonti multiple (3 URL) + parser per fonte; AAII usa `try_parsers` per consolidare il fallback interno (dataChart5 → HTML bars). Output dei moduli aggiunge `source`.

**Tech Stack:** Python 3.14 (venv), requests, stdlib, bs4

## Global Constraints

- **Venv obbligatorio**: `../.venv/bin/python` (da src/).
- Helper generico **riusabile** — DRY, una sola implementazione.
- Funzioni pure per i parser, DI per la rete.
- Catena FGI: CNN (primaria) → feargreedmeter (fallback 1) → feargreedindex (fallback 2). Tutte azionarie.
- AAII consolida il fallback interno esistente (dataChart5 → HTML bars) con `try_parsers`.
- Output moduli aggiunge `source` (es. "cnn", "feargreedmeter", "feargreedindex", "data_chart", "html_bars").
- Config `sources` per fgi (retrocompatibile se assente → default CNN).
- **compute_signal NON cambia**.
- **Il progetto NON è un repo git** → i passi "Commit" vanno saltati.
- Test suite: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`.

---

### Task 1: `fetch_utils.py` — helper generico + test

**Files:**
- Create: `src/fetch_utils.py`
- Create: `src/tests/test_fetch_utils.py`

**Interfaces:**
- Produces:
  - `fetch_first_success(session, sources, timeout, retries, backoff) -> tuple[str, str]`
  - `try_parsers(body, parsers) -> tuple[Any, str]`

- [ ] **Step 1: Scrivi i test falliti in `src/tests/test_fetch_utils.py`**

```python
"""Unit tests for the generic fetch fallback utilities."""

from __future__ import annotations

import unittest
from unittest import mock

from fetch_utils import fetch_first_success, try_parsers


def _make_session(*responses):
    """Build a fake session whose get() returns responses in sequence."""
    session = mock.Mock()
    session.get.side_effect = responses
    return session


class TestFetchFirstSuccess(unittest.TestCase):
    def test_first_source_wins(self):
        session = _make_session(
            mock.Mock(ok=True, text="body-cnn", raise_for_status=lambda: None)
        )
        body, source = fetch_first_success(
            session,
            [("cnn", "http://cnn"), ("fallback", "http://fb")],
            timeout=10, retries=1, backoff=1.0,
        )
        self.assertEqual(body, "body-cnn")
        self.assertEqual(source, "cnn")

    def test_falls_back_when_first_fails(self):
        session = _make_session(
            mock.Mock(raise_for_status=mock.Mock(side_effect=RuntimeError("boom"))),
            mock.Mock(ok=True, text="body-fb", raise_for_status=lambda: None),
        )
        body, source = fetch_first_success(
            session,
            [("cnn", "http://cnn"), ("fb", "http://fb")],
            timeout=10, retries=1, backoff=1.0,
        )
        self.assertEqual(body, "body-fb")
        self.assertEqual(source, "fb")

    def test_all_sources_fail_raises(self):
        session = _make_session(
            mock.Mock(raise_for_status=mock.Mock(side_effect=RuntimeError("a"))),
            mock.Mock(raise_for_status=mock.Mock(side_effect=RuntimeError("b"))),
        )
        with self.assertRaises(RuntimeError):
            fetch_first_success(
                session,
                [("a", "http://a"), ("b", "http://b")],
                timeout=10, retries=1, backoff=1.0,
            )


class TestTryParsers(unittest.TestCase):
    def test_first_parser_wins(self):
        def p1(body):
            return {"from": "p1"}

        def p2(body):
            return {"from": "p2"}

        result, name = try_parsers("body", [("p1", p1), ("p2", p2)])
        self.assertEqual(result["from"], "p1")
        self.assertEqual(name, "p1")

    def test_falls_back_when_first_fails(self):
        def p1(body):
            raise ValueError("no")

        def p2(body):
            return {"from": "p2"}

        result, name = try_parsers("body", [("p1", p1), ("p2", p2)])
        self.assertEqual(result["from"], "p2")
        self.assertEqual(name, "p2")

    def test_all_parsers_fail_raises(self):
        def p1(body):
            raise ValueError("no")

        with self.assertRaises(ValueError):
            try_parsers("body", [("p1", p1)])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Esegui i test per verificare che falliscano**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_fetch_utils -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetch_utils'`

- [ ] **Step 3: Implementa `src/fetch_utils.py`**

```python
"""Generic fallback helpers for scraper modules.

``fetch_first_success`` tries a list of sources in order and returns the first
that responds. ``try_parsers`` tries a list of parsers on the same body and
returns the first that succeeds. Both are used by modules whose primary source
is unstable (e.g. FGI), following the project's resilience pattern.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)


def fetch_first_success(
    session: requests.Session,
    sources: list[tuple[str, str]],
    timeout: int,
    retries: int,
    backoff: float,
) -> tuple[str, str]:
    """Fetch the first source (name, url) that responds.

    Returns:
        (body, source_name) of the first successful source.
    Raises:
        RuntimeError: If every source fails after its retries.
    """
    failures: list[str] = []
    for name, url in sources:
        try:
            return _fetch_with_retry(session, url, timeout, retries, backoff), name
        except (requests.RequestException, ValueError) as error:
            failures.append(f"{name}: {error}")
            logger.warning("Source %s failed: %s", name, error)
    raise RuntimeError(
        f"All FGI sources failed: {'; '.join(failures)}"
    )


def try_parsers(
    body: str,
    parsers: list[tuple[str, Callable[[str], Any]]],
) -> tuple[Any, str]:
    """Run the first parser (name, func) that succeeds on ``body``.

    Returns:
        (result, parser_name) of the first successful parser.
    Raises:
        ValueError: If every parser fails.
    """
    failures: list[str] = []
    for name, parser in parsers:
        try:
            return parser(body), name
        except (ValueError, KeyError, TypeError) as error:
            failures.append(f"{name}: {error}")
            logger.warning("Parser %s failed: %s", name, error)
    raise ValueError(f"All parsers failed: {'; '.join(failures)}")


def _fetch_with_retry(
    session: requests.Session,
    url: str,
    timeout: int,
    retries: int,
    backoff: float,
) -> str:
    """Fetch a URL with retry and exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.text
        except (requests.RequestException, ValueError) as error:
            last_error = error
            logger.warning(
                "Fetch attempt %d/%d failed: %s", attempt + 1, retries, error
            )
            if attempt < retries - 1:
                time.sleep(backoff * (2**attempt))
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Fetch failed after {retries} attempts")
```

- [ ] **Step 4: Esegui i test per verificare che passino**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_fetch_utils -v`
Expected: PASS (6 test)

- [ ] **Step 5: (Niente commit — progetto non è un repo git)**

---

### Task 2: FGI — catena di 3 fonti + parser

**Files:**
- Modify: `src/scrapers/fgi_scraper.py`
- Modify: `src/tests/test_fgi_scraper.py`
- Modify: `config.yaml`

**Interfaces:**
- Consumes: `fetch_first_success` + `try_parsers` dal Task 1
- Produces: `parse_cnn`, `parse_feargreedmeter`, `parse_feargreedindex`, `run()` con catena fonti e campo `source`

- [ ] **Step 1: Aggiorna i test FGI** — aggiungi i 3 parser e la catena

```python
    def test_parse_feargreedmeter(self):
        # title: "Fear and Greed Index: 67 (Greed) | Stock Market Sentiment"
        html = "<html><head><title>Fear and Greed Index: 67 (Greed) | Stock Market Sentiment</title></head></html>"
        data = parse_feargreedmeter(html)
        self.assertEqual(data["score"], 67)
        self.assertEqual(data["zone"], "greed")

    def test_parse_feargreedindex(self):
        body = '{"value":71,"label":"Greed","source":"stock"}'
        data = parse_feargreedindex(body)
        self.assertEqual(data["score"], 71)
        self.assertEqual(data["zone"], "greed")

    def test_run_marks_source_cnn(self):
        # con la CNN che risponde, source = "cnn"
        ...
```

- [ ] **Step 2: Esegui i test per verificare che falliscano**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_fgi_scraper -v`
Expected: FAIL — `parse_feargreedmeter`/`parse_feargreedindex` non esistono

- [ ] **Step 3: Implementa i parser e la catena in `fgi_scraper.py`**

```python
def parse_cnn(payload: str) -> dict[str, Any]:
    """Parse the CNN API JSON payload (primary source)."""
    import json
    data = json.loads(payload)
    fng = data["fear_and_greed"]
    score = float(fng["score"])
    zone = fng.get("rating") or zone_from_score(score)
    return {"score": score, "zone": zone}


def parse_feargreedmeter(html: str) -> dict[str, Any]:
    """Parse the feargreedmeter.com title: 'Fear and Greed Index: N (Label)'."""
    m = re.search(r"Fear and Greed Index:\s*([\d.]+)\s*\(([^)]+)\)", html)
    if not m:
        raise ValueError("feargreedmeter value not found in HTML")
    score = float(m.group(1))
    zone = m.group(2).strip().lower()
    return {"score": score, "zone": zone}


def parse_feargreedindex(body: str) -> dict[str, Any]:
    """Parse the feargreedindex.net API JSON payload."""
    import json
    data = json.loads(body)
    score = float(data["value"])
    zone = str(data.get("label", "")).strip().lower()
    return {"score": score, "zone": zone}
```

E modifica `run()`:

```python
def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    sources = config.get("sources") or [
        {"name": "cnn", "url": FGI_API_URL},
        {"name": "feargreedmeter", "url": FGI_METER_URL},
        {"name": "feargreedindex", "url": FGI_INDEX_URL},
    ]
    source_list = [(s["name"], s["url"]) for s in sources]
    timeout = config.get("timeout", DEFAULT_TIMEOUT)
    retries = config.get("retries", DEFAULT_RETRIES)
    backoff = config.get("backoff", DEFAULT_BACKOFF)
    headers = config.get("headers", DEFAULT_HEADERS)

    parsers = {
        "cnn": parse_cnn,
        "feargreedmeter": parse_feargreedmeter,
        "feargreedindex": parse_feargreedindex,
    }

    with requests.Session() as session:
        session.headers.update(headers)
        body, source = fetch_first_success(session, source_list, timeout, retries, backoff)

    parser_list = [(source, parsers[source])]
    data, _ = try_parsers(body, parser_list)
    result = build_result(data["score"], data["zone"], _now_iso())
    result["source"] = source
    return result
```

Aggiungi le costanti URL:
```python
FGI_API_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
FGI_METER_URL = "https://feargreedmeter.com/"
FGI_INDEX_URL = "https://feargreedindex.net/api/fear-greed"
```

- [ ] **Step 4: Esegui i test per verificare che passino**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_fgi_scraper -v`
Expected: PASS (test esistenti + nuovi parser)

- [ ] **Step 5: Aggiorna `config.yaml`** — aggiungi `sources` al config di fgi

```yaml
  fgi:
    module: scrapers.fgi_scraper
    output_key: fgi
    schedule: daily
    config:
      sources:
        - name: cnn
          url: "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        - name: feargreedmeter
          url: "https://feargreedmeter.com/"
        - name: feargreedindex
          url: "https://feargreedindex.net/api/fear-greed"
      timeout: 15
      retries: 3
      backoff: 2.0
      headers:
        User-Agent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        Accept: "application/json"
        Referer: "https://www.cnn.com/"
        Origin: "https://www.cnn.com"
```

- [ ] **Step 6: Verifica con fonti reali**

Run: `cd src && ../.venv/bin/python -c "from scrapers.fgi_scraper import run; print(run())"`
Expected: dict con score reale + `source: "cnn"` (CNN risponde)

- [ ] **Step 7: (Niente commit — progetto non è un repo git)**

---

### Task 3: AAII — consolidamento fallback con `try_parsers`

**Files:**
- Modify: `src/scrapers/aaii_scraper.py`
- Modify: `src/tests/test_aaii_scraper.py`

**Interfaces:**
- Consumes: `try_parsers` dal Task 1
- Produces: `run()` con `try_parsers([data_chart, html_bars])` e campo `source`

- [ ] **Step 1: Aggiorna i test AAII** — verifica `source` nel run

```python
    def test_run_source_data_chart(self):
        # HTML con dataChart5 valido → source "data_chart"
        ...

    def test_run_source_html_bars(self):
        # HTML con solo bars → source "html_bars"
        ...
```

- [ ] **Step 2: Esegui i test per verificare che falliscano**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_aaii_scraper -v`
Expected: FAIL — test `source` non presenti / run non marca source

- [ ] **Step 3: Modifica `run()` in `aaii_scraper.py`**

Sostituisci il try/except manuale con `try_parsers`:

```python
    from fetch_utils import try_parsers

    html = _fetch_with_retry(session, url, timeout, retries, backoff)
    data, parser_name = try_parsers(
        html,
        [("data_chart", parse_data_chart), ("html_bars", parse_html_bars)],
    )
    result = build_result(data["bullish"], data["bearish"], data["neutral"], _now_iso())
    result["source"] = parser_name
    return result
```

Nota: l'import `from fetch_utils import try_parsers` va messo in cima al modulo
(con gli altri import), non dentro run(). `parse_data_chart` e `parse_html_bars`
sono le funzioni esistenti (già sollevano ValueError se falliscono).

- [ ] **Step 4: Esegui i test per verificare che passino**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_aaii_scraper -v`
Expected: PASS (test esistenti + nuovi source)

- [ ] **Step 5: (Niente commit — progetto non è un repo git)**

---

### Task 4: Report HTML — card mostra `source` + docs

**Files:**
- Modify: `src/report_html.py`
- Modify: `src/tests/test_report_html.py`
- Modify: `README.md`
- Modify: `.opencode/context/project-intelligence/scraping-patterns.md`
- Modify: `.opencode/context/project-intelligence/technical-domain.md`
- Modify: `.opencode/context/project-intelligence/navigation.md`

**Interfaces:**
- Consumes: campo `source` dai moduli
- Produces: card con fonte, docs aggiornati

- [ ] **Step 1: Aggiungi `source` alla card FGI in `render_market_cards`**

```python
    fgi_source = fgi.get("source")
    source_html = f' · Fonte: {html_mod.escape(fgi_source)}' if fgi_source else ""
    ...
    f'<div class="meta">Aggiornato: {format_iso_dt(fgi.get("fetched_at"))}{source_html}</div>'
```

- [ ] **Step 2: Aggiungi `source` alla card AAII**

Analogamente, aggiungi la fonte nella card AAII.

- [ ] **Step 3: Aggiungi test report_html per source**

```python
    def test_market_cards_shows_fgi_source(self):
        data = _sample_data()
        data["fgi"]["source"] = "feargreedmeter"
        html = render_market_cards(data)
        self.assertIn("Fonte: feargreedmeter", html)
```

- [ ] **Step 4: Esegui la suite completa**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 5: Aggiorna la documentazione**

- README: tabella "Stato dei moduli" — nota fallback FGI/AAII
- scraping-patterns.md: sezione "Fallback fonti generico (fetch_utils.py)" con il pattern
- technical-domain.md: Codebase References per fetch_utils.py
- navigation.md: log + version bump

- [ ] **Step 6: Esegui la suite completa**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 7: (Niente commit — progetto non è un repo git)**
