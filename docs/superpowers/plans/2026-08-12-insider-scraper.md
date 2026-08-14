# Insider Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementare `insider_scraper.py` (bonus insider della strategia H5 da OpenInsider) e integrarlo nel report HTML come card con legenda.

**Architecture:** Modulo scraper `run(config) -> dict` che legge la pagina OpenInsider "Latest Officer Purchases $25k+" via HTTP (HTTPS fallisce sul server), estrae le righe della tabella `tinytable`, filtra gli acquisti recenti (P - Purchase, 30 giorni), calcola i bonus per i 29 ticker del config (+0.5 officer, +1.0 CEO/CFO, max 1.5). Non entra in compute_signal.

**Tech Stack:** Python 3.14 (venv), requests, stdlib (re, json, datetime)

## Global Constraints

- **Venv obbligatorio**: `../.venv/bin/python` (da src/).
- **Fonte via HTTP** (`http://openinsider.com/`) — HTTPS fallisce sul server.
- Contratto scraper `run(config) -> dict` con funzioni pure.
- Bonus strategia H5: ≥2 acquisti + valore >$100K → +0.5; CEO/CFO → +1.0; max 1.5.
- **compute_signal NON cambia** — l'insider è bonus opportunità, non scoring ticker.
- **Il progetto NON è un repo git** → i passi "Commit" vanno saltati.
- Test suite: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`.

---

### Task 1: `insider_scraper.py` — modulo + test

**Files:**
- Create: `src/scrapers/insider_scraper.py`
- Create: `src/tests/test_insider_scraper.py`

**Interfaces:**
- Consumes: `config` (url, timeout, retries, backoff, headers, days_back, min_value, stale_after_hours), `config["tickers"]` iniettato
- Produces:
  - `parse_rows(html: str) -> list[dict]`
  - `filter_recent(rows: list[dict], days_back: int = 30) -> list[dict]`
  - `compute_bonuses(rows: list[dict], tickers: dict, min_value: int = 100000) -> dict`
  - `build_result(per_ticker: dict, fetched_at: str | None = None) -> dict`
  - `fetch_page(session, url, timeout) -> str`
  - `run(config: dict | None = None) -> dict`

- [ ] **Step 1: Scrivi i test falliti in `src/tests/test_insider_scraper.py`**

```python
"""Unit tests for the insider scraper (pure functions, no network)."""

from __future__ import annotations

import unittest

from scrapers.insider_scraper import (
    build_result,
    compute_bonuses,
    filter_recent,
    parse_rows,
)

# HTML mock con la struttura reale della tabella OpenInsider (tinytable)
_HTML_SAMPLE = """
<table class="tinytable"><thead><tr>
<th><h3>Filing Date</h3></th><th><h3>Trade Date</h3></th>
<th><h3>Ticker</h3></th><th><h3>Insider Name</h3></th>
<th><h3>Title</h3></th><th><h3>Trade Type</h3></th>
<th><h3>Price</h3></th><th><h3>Qty</h3></th><th><h3>Value</h3></th>
</tr></thead><tbody>
<tr><td><a href="http://sec.gov/form4.xml">2026-08-12 18:00:06</a></td>
<td><div>2026-08-10</div></td>
<td><b><a href="/ACDC">ACDC</a></b></td>
<td><a href="/insider/Wilks-Matthew/1">Wilks Matthew</a></td>
<td>CEO</td><td>P - Purchase</td>
<td>$5.02</td><td>+80,000</td><td>+$401,851</td></tr>
<tr><td><a href="http://sec.gov/form4.xml">2026-08-12 17:08:22</a></td>
<td><div>2026-08-10</div></td>
<td><b><a href="/MTDR">MTDR</a></b></td>
<td><a href="/insider/Elsener-William/2">Elsener William Thomas</a></td>
<td>EVP, Reservoir Engineering</td><td>P - Purchase</td>
<td>$50.94</td><td>+850</td><td>+$43,299</td></tr>
<tr><td><a href="http://sec.gov/form4.xml">2026-08-12 16:00:00</a></td>
<td><div>2026-08-10</div></td>
<td><b><a href="/ACDC">ACDC</a></b></td>
<td><a href="/insider/Other/3">Other Person</a></td>
<td>Director</td><td>S - Sale</td>
<td>$6.00</td><td>+100</td><td>+$600</td></tr>
</tbody></table>
"""


class TestParseRows(unittest.TestCase):
    def test_parses_rows(self):
        rows = parse_rows(_HTML_SAMPLE)
        self.assertEqual(len(rows), 3)
        first = rows[0]
        self.assertEqual(first["ticker"], "ACDC")
        self.assertEqual(first["role"], "CEO")
        self.assertEqual(first["trade_type"], "P - Purchase")
        self.assertEqual(first["price"], 5.02)
        self.assertEqual(first["qty"], 80000)
        self.assertEqual(first["value"], 401851)
        self.assertEqual(first["trade_date"], "2026-08-10")

    def test_empty_html_returns_empty(self):
        self.assertEqual(parse_rows("<html></html>"), [])


class TestFilterRecent(unittest.TestCase):
    def test_keeps_only_purchases(self):
        rows = parse_rows(_HTML_SAMPLE)
        filtered = filter_recent(rows, days_back=30)
        # solo P - Purchase (2 righe), la S - Sale esclusa
        self.assertEqual(len(filtered), 2)
        self.assertTrue(all(r["trade_type"] == "P - Purchase" for r in filtered))


class TestComputeBonuses(unittest.TestCase):
    def test_officer_and_ceo_bonus(self):
        rows = parse_rows(_HTML_SAMPLE)
        tickers = {
            "semiconductors": [{"symbol": "ACDC", "name": "A"}],
            "defense": [{"symbol": "MTDR", "name": "M"}],
        }
        result = compute_bonuses(rows, tickers)
        # ACDC: 1 purchase (CEO) → ceo_cfo_bonus 1.0
        acdc = result["semiconductors"]["ACDC"]
        self.assertEqual(acdc["purchases_30d"], 1)
        self.assertTrue(acdc["ceo_cfo"])
        self.assertEqual(acdc["ceo_cfo_bonus"], 1.0)
        # MTDR: 1 purchase EVP < 2 → nessun officer bonus
        mtdr = result["defense"]["MTDR"]
        self.assertEqual(mtdr["purchases_30d"], 1)
        self.assertEqual(mtdr["officer_bonus"], 0.0)

    def test_officer_bonus_requires_two_purchases_and_value(self):
        rows = [
            {"ticker": "NVDA", "role": "VP", "trade_type": "P - Purchase",
             "value": 60000, "price": 100.0, "qty": 600, "trade_date": "2026-08-10"},
            {"ticker": "NVDA", "role": "VP", "trade_type": "P - Purchase",
             "value": 60000, "price": 100.0, "qty": 600, "trade_date": "2026-08-11"},
        ]
        tickers = {"semiconductors": [{"symbol": "NVDA", "name": "N"}]}
        result = compute_bonuses(rows, tickers)
        nvda = result["semiconductors"]["NVDA"]
        self.assertEqual(nvda["purchases_30d"], 2)
        self.assertEqual(nvda["total_value_30d"], 120000)
        # 2 acquisti + valore > 100K → officer bonus 0.5
        self.assertEqual(nvda["officer_bonus"], 0.5)


class TestBuildResult(unittest.TestCase):
    def test_builds_file_json_shape(self):
        per_ticker = {
            "semiconductors": {"NVDA": {"purchases_30d": 2, "total_value_30d": 120000,
                                         "ceo_cfo": False, "officer_bonus": 0.5,
                                         "ceo_cfo_bonus": 0.0, "total_bonus": 0.5,
                                         "last_trade_date": "2026-08-11"}},
            "total": {"tickers_with_bonus": 1, "max_bonus": 0.5, "max_ticker": "NVDA"},
        }
        result = build_result(per_ticker, fetched_at="2026-08-12T00:00:00+00:00")
        self.assertEqual(result["total"]["max_bonus"], 0.5)
        self.assertEqual(result["frequency"], "daily")
        self.assertEqual(result["status"], "fresh")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Esegui i test per verificare che falliscano**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_insider_scraper -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scrapers.insider_scraper'`

- [ ] **Step 3: Implementa `src/scrapers/insider_scraper.py`**

```python
"""Insider transactions scraper module.

Reads the OpenInsider "Latest Officer Purchases $25k+" page and computes the
insider-buying bonus of the buy-the-dip strategy (specifiche_strategia.md H5):
- +0.5 if >= 2 officer open-market purchases in the last 30 days, value > $100K
- +1.0 if a CEO/CFO purchased on the open market
- cumulative, capped at +1.5

NOTE: OpenInsider only answers over HTTP (HTTPS connection is refused by the
server). The officer page already includes CEO/CFO transactions, identified by
the Title column, so a single page is scanned.

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

OPENINSIDER_OFFICER_URL = "http://openinsider.com/latest-officer-purchases-25k"

DEFAULT_TIMEOUT = 20
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 2.0
DEFAULT_DAYS_BACK = 30
DEFAULT_MIN_VALUE = 100000
DEFAULT_STALE_AFTER_HOURS = 24
FREQUENCY = "daily"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_CEO_CFO_ROLES = re.compile(
    r"\b(CEO|CFO|Chief Executive Officer|Chief Financial Officer)\b", re.IGNORECASE
)


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _num(value: str) -> float:
    """Parse a formatted number like '+80,000' or '+$401,851' to float."""
    cleaned = value.replace("$", "").replace(",", "").replace("+", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_rows(html: str) -> list[dict[str, Any]]:
    """Extract transaction rows from the OpenInsider tinytable.

    Returns a list of dicts with ticker, insider, role, trade_type, price,
    qty, value and trade_date.
    """
    rows: list[dict[str, Any]] = []
    # Match each <tr> inside the results table. Rows have >5 <td> cells.
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 9:
            continue
        ticker_m = re.search(r'href="/[A-Z0-9.-]+"[^>]*>([A-Z0-9.-]+)</a>', tds[3])
        if not ticker_m:
            continue
        # trade_date è nel secondo div della colonna Trade Date (td[1])
        date_m = re.search(r"<div>(.*?)</div>", tds[1])
        if not date_m:
            continue
        # title (td[5]), trade_type (td[6]), price (td[7]), qty (td[8]), value (td[9])
        role = re.sub(r"<[^>]+>", "", tds[5]).strip()
        trade_type = re.sub(r"<[^>]+>", "", tds[6]).strip()
        rows.append(
            {
                "ticker": ticker_m.group(1),
                "insider": re.sub(r"<[^>]+>", "", tds[4]).strip(),
                "role": role,
                "trade_type": trade_type,
                "price": _num(re.sub(r"<[^>]+>", "", tds[7])),
                "qty": _num(re.sub(r"<[^>]+>", "", tds[8])),
                "value": _num(re.sub(r"<[^>]+>", "", tds[9])),
                "trade_date": date_m.group(1).strip(),
            }
        )
    return rows


def filter_recent(rows: list[dict[str, Any]], days_back: int = DEFAULT_DAYS_BACK) -> list[dict[str, Any]]:
    """Keep only open-market purchases within the last days_back days."""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days_back)
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if row["trade_type"] != "P - Purchase":
            continue
        try:
            trade_date = datetime.strptime(row["trade_date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if trade_date >= cutoff:
            filtered.append(row)
    return filtered


def compute_bonuses(
    rows: list[dict[str, Any]],
    tickers: dict[str, Any],
    min_value: int = DEFAULT_MIN_VALUE,
) -> dict[str, dict[str, Any]]:
    """Compute insider bonuses per configured ticker.

    Returns dict keyed by category with per-ticker stats, plus a "total" key.
    """
    result: dict[str, dict[str, Any]] = {}
    all_tickers_with_bonus: list[tuple[str, float]] = []

    for category, entries in tickers.items():
        result[category] = {}
        for entry in entries:
            symbol = entry["symbol"]
            purchases = [r for r in rows if r["ticker"] == symbol]
            if not purchases:
                continue
            total_value = sum(r["value"] for r in purchases)
            ceo_cfo = any(_CEO_CFO_ROLES.search(r["role"]) for r in purchases)
            officer_bonus = 0.5 if (len(purchases) >= 2 and total_value > min_value) else 0.0
            ceo_cfo_bonus = 1.0 if ceo_cfo else 0.0
            total_bonus = round(min(officer_bonus + ceo_cfo_bonus, 1.5), 1)
            result[category][symbol] = {
                "purchases_30d": len(purchases),
                "total_value_30d": int(total_value),
                "ceo_cfo": ceo_cfo,
                "officer_bonus": officer_bonus,
                "ceo_cfo_bonus": ceo_cfo_bonus,
                "total_bonus": total_bonus,
                "last_trade_date": max(r["trade_date"] for r in purchases),
            }
            if total_bonus > 0:
                all_tickers_with_bonus.append((symbol, total_bonus))

    if all_tickers_with_bonus:
        max_ticker, max_bonus = max(all_tickers_with_bonus, key=lambda x: x[1])
        result["total"] = {
            "tickers_with_bonus": len(all_tickers_with_bonus),
            "max_bonus": max_bonus,
            "max_ticker": max_ticker,
        }
    else:
        result["total"] = {"tickers_with_bonus": 0, "max_bonus": 0.0, "max_ticker": None}
    return result


def build_result(
    per_ticker: dict[str, dict[str, Any]],
    fetched_at: str | None = None,
    stale_after_hours: int = DEFAULT_STALE_AFTER_HOURS,
) -> dict[str, Any]:
    """Build the output dict in the file.json format."""
    result: dict[str, Any] = {key: dict(value) for key, value in per_ticker.items()}
    result["fetched_at"] = fetched_at or _now_iso()
    result["frequency"] = FREQUENCY
    result["stale_after_hours"] = stale_after_hours
    result["status"] = "fresh"
    return result


def fetch_page(
    session: requests.Session,
    url: str = OPENINSIDER_OFFICER_URL,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Fetch the OpenInsider officer purchases page (HTTP)."""
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
                "Insider fetch attempt %d/%d failed: %s", attempt + 1, retries, error
            )
            if attempt < retries - 1:
                time.sleep(backoff * (2**attempt))
    raise RuntimeError(f"Insider fetch failed after {retries} attempts: {last_error}")


def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch insider purchases and compute the strategy bonus.

    Args:
        config: Overrides + injected ``tickers``.
    """
    config = config or {}
    tickers = config.get("tickers", {})
    url = config.get("url", OPENINSIDER_OFFICER_URL)
    timeout = config.get("timeout", DEFAULT_TIMEOUT)
    retries = config.get("retries", DEFAULT_RETRIES)
    backoff = config.get("backoff", DEFAULT_BACKOFF)
    headers = config.get("headers", DEFAULT_HEADERS)
    days_back = config.get("days_back", DEFAULT_DAYS_BACK)
    min_value = config.get("min_value", DEFAULT_MIN_VALUE)

    with requests.Session() as session:
        session.headers.update(headers)
        html = _fetch_with_retry(session, url, timeout, retries, backoff)

    rows = parse_rows(html)
    recent = filter_recent(rows, days_back=days_back)
    per_ticker = compute_bonuses(recent, tickers, min_value=min_value)
    return build_result(
        per_ticker,
        stale_after_hours=config.get("stale_after_hours", DEFAULT_STALE_AFTER_HOURS),
    )
```

- [ ] **Step 4: Esegui i test per verificare che passino**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_insider_scraper -v`
Expected: PASS (6 test)

- [ ] **Step 5: Verifica con la pagina reale**

Run: `cd src && ../.venv/bin/python -c "from scrapers.insider_scraper import run; print(run({'tickers': {'semiconductors': [{'symbol': 'NVDA', 'name': 'N'}]}}))"`
Expected: dict con purchases/bonus reali (o total 0 se nessun acquisto NVDA recente)

- [ ] **Step 6: (Niente commit — progetto non è un repo git)**

---

### Task 2: Config.yaml + Report HTML (card insider)

**Files:**
- Modify: `config.yaml`
- Modify: `src/report_html.py`
- Modify: `src/tests/test_report_html.py`

**Interfaces:**
- Consumes: `insider_scraper.run(config)` dal Task 1
- Produces: sezione `insider` in config, card "Insider" nel report, voce legenda

- [ ] **Step 1: Aggiungi `insider` in config.yaml** (dopo pct_sma, prima di tickers)

```yaml
  insider:
    module: scrapers.insider_scraper
    output_key: insider
    schedule: daily
    config:
      url: "http://openinsider.com/latest-officer-purchases-25k"
      timeout: 20
      retries: 3
      backoff: 2.0
      headers:
        User-Agent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
      days_back: 30
      min_value: 100000
      stale_after_hours: 24
```

- [ ] **Step 2: Aggiungi la card insider in `render_market_cards`** (dopo card breadth)

```python
    insider = data.get("insider", {})
    total_ins = insider.get("total", {})
    n_bonus = total_ins.get("tickers_with_bonus", 0)
    max_bonus = total_ins.get("max_bonus", 0.0)
    max_ticker = total_ins.get("max_ticker")
    max_html = f'<span class="ticker">{html_mod.escape(str(max_ticker))}</span>' if max_ticker else "—"
    parts.append(
        '<div class="card"><div class="label">Insider (bonus)</div>'
        f'<div class="value">{n_bonus} titoli</div>'
        f'<div class="meta">Max bonus {fmt(max_bonus)} ({max_html})</div>'
        f'<div class="meta">Aggiornato: {format_iso_dt(insider.get("fetched_at"))}</div></div>'
    )
```

- [ ] **Step 3: Aggiungi la voce insider in `_LEGEND_MARKET`**

```python
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
```

- [ ] **Step 4: Aggiungi test report_html per insider**

```python
    def test_market_cards_contains_insider(self):
        data = _sample_data()
        data["insider"] = {"total": {"tickers_with_bonus": 2, "max_bonus": 1.0,
                                     "max_ticker": "NVDA"},
                           "fetched_at": "2026-08-12T00:00:00+00:00"}
        html = render_market_cards(data)
        self.assertIn("Insider", html)
        self.assertIn("2 titoli", html)
        self.assertIn("NVDA", html)

    def test_insider_legend_entry(self):
        html = render_legend()
        self.assertIn("Insider", html)
        self.assertIn("max +1.5", html)
```

- [ ] **Step 5: Esegui la suite completa**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 6: (Niente commit — progetto non è un repo git)**

---

### Task 3: Documentazione — README + context

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
| `insider_scraper.py` | OpenInsider (HTTP) | Bonus insider (acquisti dirigenti/CEO/CFO) | giornaliera |
```
```markdown
| `insider_scraper.py` | ✅ Funzionante | Bonus H5 da OpenInsider (HTTPS non risponde → HTTP) |
```
E Roadmap: spunta `insider_scraper` (e la riga "SMA, Insider" → rimuovi Insider).

- [ ] **Step 2: Aggiorna scraping-patterns.md** — sezione "Insider: OpenInsider via HTTP"

```markdown
## Insider: OpenInsider via HTTP (non HTTPS!)
OpenInsider risponde SOLO su HTTP (HTTPS: connessione rifiutata dal server).
La pagina `/latest-officer-purchases-25k` include anche CEO/CFO (colonna Title).
Filtrare `P - Purchase`, ultimi 30 giorni, bonus H5: +0.5 (≥2 acquisti, valore
>$100K), +1.0 (CEO/CFO), max +1.5.
```

- [ ] **Step 3: Aggiorna technical-domain.md** — Codebase References

```markdown
**Scraper Insider**: `src/scrapers/insider_scraper.py` — bonus H5 da OpenInsider (HTTP, solo acquisti)
```

- [ ] **Step 4: Aggiorna navigation.md** — log

```markdown
- **2026-08-12**: insider_scraper.py (bonus H5 da OpenInsider) — scraping-patterns.md v1.4, technical-domain.md v1.8, navigation.md v1.6
```

- [ ] **Step 5: Esegui la suite completa**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 6: (Niente commit — progetto non è un repo git)**
