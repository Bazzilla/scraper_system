# AGENTS.md

Sistema **config-driven** di scraping finanziario: un orchestratore legge `config.yaml`, esegue gli scraper in sequenza, consolida i risultati in `output/output.json`, registra ogni esecuzione su SQLite (`output/scraper_audit.db`) e genera un report HTML statico (`output/report.html`).

## Comandi essenziali

Tutto va eseguito con il Python del venv (sistema PEP 668, niente install globale):

```bash
# Test (DA src/, import relativi) — 224 test, ~0.2s
cd src && ../.venv/bin/python -m unittest discover -s tests

# Pipeline completa (dalla radice): orchestrazione + report
./.venv/bin/python run.py

# Solo report HTML dall'output esistente (nessuno scraping)
./.venv/bin/python run.py --report-only

# Riapplica manual_overrides.yaml all'output esistente (nessuno scraping)
./.venv/bin/python run.py --override-only

# Scheduler: esecuzione singola ora
cd src && ../.venv/bin/python scheduler.py --config ../config.yaml --once
```

## Struttura

- **`run.py`** (radice) — entry point unico, 3 modalità (full / `--report-only` / `--override-only`); risolve i path dalla propria posizione, funziona da qualsiasi directory
- **`src/`** — `orchestrator.py` (entry point), `scheduler.py`, `config_loader.py`, `registry.py`, `consolidator.py`, `audit.py`, `report_html.py`, `fetch_utils.py`, `indicator_registry.py`, `manual_overrides.py`
- **`src/scrapers/`** — i moduli scraper (7): `fgi_scraper.py`, `aaii_scraper.py`, `vix_scraper.py`, `pcr_scraper.py`, `ohlcv_fetcher.py`, `indicators.py`, `insider_scraper.py`
- **`src/tests/`** — test unitari `unittest` (funzioni pure, mock, nessuna rete)
- **`config.yaml`** (radice) — chi/quando/dove + sezione `tickers` + `strategy` (indicator_registry, proxy_accepted, manual_overrides, force_manual_overrides)
- **`indicator_registry.yaml`** + **`manual_overrides.yaml`** (radice) — matrice indicatori e override manuali
- **`output/`** — `output.json`, `scraper_audit.db`, `report.html`, `ohlcv_cache.json` (cache intermedia OHLCV)
- **`deploy/systemd/`** — unità service+timer per esecuzione daily
- **`docs/strategy/`** — strategia buy-the-dip (riferimento per `compute_signal`)

## Contratto scraper

Ogni modulo in `src/scrapers/` espone `run(config: dict) -> dict` e ritorna un dict strutturato con `fetched_at`, `frequency`, `stale_after_hours`, `status`. Pattern: funzioni pure di parse/build separate dal fetch, retry con backoff, header browser.

**Per aggiungere un nuovo scraper**:
1. Crea `src/scrapers/<nome>_scraper.py` con `run(config) -> dict`
2. Aggiungi la voce in `config.yaml` sotto `scrapers:` (module, output_key, schedule, config)
3. Aggiungi un test in `src/tests/test_<nome>_scraper.py`
4. **Aggiorna `src/report_html.py`** (render_market_cards / _ticker_sections / render_ticker_table) — manutenibilità esplicita
5. Esegui l'orchestratore per verificare

**Indicatori non scrapabili** (alimentabili a mano via `manual_overrides.yaml`): `naaim`, `vix_term_structure`, `pct_sma` (breadth mercato USA, F3/#13-14). Il registry (`indicator_registry.yaml`) li marca `manual_supported`.

## Convenzioni e gotcha

- **Venv obbligatorio**: `.venv/bin/python` sempre (PEP 668); dipendenze in `requirements.txt` (pin esatte)
- **pandas-ta è ESCLUSO** (numba incompatibile con Python 3.14) → usare `ta` 0.11.0
- **Fail-closed (consolidator)**: un modulo fallito NON sparisce — compare con `status: "error"`; `signal_reliability: "low"` se errori o 0 sorgenti
- **Priorità dati**: scraping (fresh) > manual override (valido+fresco) > missing/error; "scraping wins" vale SOLO per `origin == "scraped"` — un manual persistito non blocca un override YAML più recente
- **Separazione semantica**: `coverage` (statico) ≠ `availability` (dinamico) ≠ `usable_in_strategy_score` (derivato, fail-closed); un proxy non entra mai nello score senza `proxy_accepted` esplicito; un manual override valido e fresco rende un indicatore `manual_supported` usabile nello score
- **Isolamento per-ticker**: un ticker che fallisce non blocca gli altri; l'orchestratore inietta `tickers` e risolve `cache_path`
- **Rate limiting**: `request_delay` (default 1.0s) tra i fetch dei ticker in `ohlcv_fetcher` (previene HTTP 429 di Yahoo)
- **Naming**: snake_case per file/funzioni/config keys/JSON keys; lowercase per origin/coverage/segnale; uppercase per badge (COMPRA/WATCHLIST/ATTENDI)
- **⚠️ `.gitignore` contiene un marcatore di merge conflict committato** (`<<<<<<< HEAD` alla riga 1) — è intenzionale/storico, non un conflitto in corso; non "fixarlo" senza chiedere

## Contesto di progetto

I pattern dettagliati vivono in `.opencode/context/project-intelligence/` (fonte di verità):
- `technical-domain.md` — stack, architettura, naming, standard, security, strategy registry & manual override
- `scraping-patterns.md` — pattern scraper per modulo
- `report-html.md` — pattern report HTML + segnale con gate FGI
- `aaii-scraping-guide.md` — dettaglio scraping AAII

Leggili prima di modificare codice che tocca questi pattern.