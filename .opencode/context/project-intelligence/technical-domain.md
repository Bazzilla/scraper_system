<!-- Context: project-intelligence/technical | Priority: critical | Version: 1.12 | Updated: 2026-08-14 -->

# Technical Domain

**Purpose**: Tech stack, architettura, naming, standard e security di scraper-system — un sistema config-driven che esegue scraping di informazioni finanziarie da più fonti, consolida i dati in un JSON strutturato, registra ogni esecuzione su SQLite e genera un report HTML statico.
**Last Updated**: 2026-08-14

## Quick Reference
**Update Triggers**: Cambio tech stack | Nuovi moduli scraper | Cambio formato config/output | Decisioni architetturali | Modifiche alla strategia di trading
**Audience**: Sviluppatori, agenti AI

## Primary Stack
| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Language | Python 3.14 (venv, PEP 668) | Ricco di librerie per scraping e indicatori |
| Scraping | requests + BeautifulSoup | Pagine statiche, leggero |
| Data (OHLCV) | yfinance 1.5.2 | Fetch dati finanziari da Yahoo Finance |
| Indicators | ta 0.11.0 | RSI(14), OBV, MFI(14), SMA(50), SMA(200), drawdown 52w |
| Report HTML | stdlib + pyyaml | Pagina statica self-contained (dark+light, semafori) |
| Storage | SQLite + JSON | Audit log per esecuzione + output consolidato |
| Config | YAML | "Chi scrapare, quando, dove sta lo script" + registry indicatori + manual overrides |
| Scheduling | Scheduler OS o schedule Python | Esecuzione giornaliera/settimanale |

> **⚠️ pandas-ta è ESCLUSO**: dipende da `numba` che non supporta Python 3.14. Sostituito da `ta` 0.11.0. L'ambiente è Arch/PEP 668 → dipendenze in **venv** (non a livello di sistema). Strategia di trading in `/home/fibbione/Temp/strategia_trading/` (fuori dal progetto).

## Architecture
Orchestratore config-driven in `src/`. Flusso: `config_loader` legge `config.yaml` → `registry` risolve ogni modulo → `orchestrator.run()` esegue gli scraper in sequenza → `manual_overrides` applica eventuali valori manuali (priorità scraping > manual > missing) → `consolidator` costruisce il JSON → `audit` scrive su SQLite → `report_html.render()` genera la pagina. Un errore in un modulo **non blocca** gli altri, ma viene **registrato** nell'output (fail-closed). `scheduler.py` esegue l'intera orchestrazione secondo la sezione `scheduler:` di config.yaml (loop o `--once`).

```
config.yaml → config_loader → registry → orchestrator.run()
                                         → manual_overrides (fallback manuale validato)
                                         → consolidator → output/output.json
                                         → audit → output/scraper_audit.db
                                         → report_html → output/report.html
scheduler.py (--once | loop) → orchestrator.run() [secondo scheduler: in config]
```

## Pattern di riferimento (deep dive)
- **Scraping**: pattern per modulo in `scraping-patterns.md` (FGI, VIX, AAII, OHLCV, Indicators, PCR, PCT SMA, Insider, config YAML, tickers)
- **Report HTML**: pattern del segnale COMPRA/WATCHLIST/ATTENDI con gate FGI in `report-html.md`
- **Strategy Registry & Manual Override**: sezione sotto — stato per indicatore (coverage/availability/usable) e override manuali validati

## Strategy Registry & Manual Override
- **`indicator_registry.py` + `indicator_registry.yaml`** — matrice machine-readable che dichiara per ogni indicatore della strategia i campi **statici** `coverage` e `implementation_status` (implemented/proxy/missing/manual_supported), più `semantic_coherent` e `output_key`. Ogni run calcola i campi **dinamici**:
  - `coverage` (**statico, dalle specifiche strategiche**): true = l'indicatore **appartiene alla strategia** (citato in `specifiche_strategia.md`). NON dipende dal runtime: resta true anche se non implementato, rotto, non scrapabile, disponibile solo manualmente o non usabile nello scoring. false = artefatto informativo NON strategico (es. VIX spot).
  - `implementation_status` (**statico**): `implemented` (modulo con semantica equivalente) · `proxy` (dato diverso che approssima l'indicatore, o artefatto informativo) · `missing` (gap dichiarato) · `manual_supported` (nessuno scraper, ma supporto via `manual_overrides.yaml`)
  - `availability` (**dinamico**): il modulo ha prodotto `status: "fresh"` oppure esiste un manual override valido e fresco
  - `usable_in_strategy_score` (**derivato**): true solo se `coverage=true` E `availability=true` E implementation_status in (implemented, manual_supported), oppure proxy esplicitamente in `strategy.proxy_accepted` E disponibile (fail-closed: coverage=false mai, missing mai, non disponibile mai)
  - `source` (**dinamico**): `scraped` | `manual` | `missing`
- **`manual_overrides.py` + `manual_overrides.yaml`** — valori inseriti manualmente per indicatori fragili (aaii, fgi, naaim). Priorità **scraping > manual > missing**. Regole:
  - override **validato** prima dell'uso; malformato → log + ignorato (non rompe il pipeline)
  - scadenza da `stale_after_hours` dopo `fetched_at`; scaduto → `status: stale`, mai usable
  - tracciato: `source: "manual"`, `origin: "manual"`, `entered_by`, `note` — mai confuso con uno scrapato
  - `strategy.force_manual_overrides` forza il manuale su scraper fresh — **disabilitato di default**
  - un override **non altera `coverage`** (statico) — es. NAAIM resta `coverage: true, implementation_status: manual_supported` anche quando non alimentato

## Naming Conventions
| Type | Convention | Example |
|------|-----------|---------|
| Files | snake_case | fear_greed_scraper.py |
| Functions | snake_case | fetch_fgi(), run() |
| Config keys | snake_case | stale_after_hours, cache_path, request_delay |
| JSON keys | snake_case | fetched_at, drawdown_52w, rsi_14, sma_50 |
| Origin keys | lowercase | scraped, manual, missing |
| Coverage keys | lowercase | coverage, implementation_status, availability, usable_in_strategy_score |
| Segnale classes | lowercase | buy, watchlist, hold |
| Badge label | uppercase | COMPRA, WATCHLIST, ATTENDI |

## Code Standards
- Type hints su tutte le funzioni e moduli
- Error handling + retry con backoff per modulo
- Validazione config YAML tramite schema (`config_loader`)
- Audit log SQLite per ogni esecuzione (cosa, quando, esito)
- Moduli indipendenti: ogni scraper è isolato e testabile
- Orchestratore gestisce sequenza, errori e consolidamento
- Funzioni pure per la logica di parse (testabili senza rete)
- **Isolamento per-ticker**: un ticker che fallisce non blocca gli altri
- **Iniezione `tickers`**: l'orchestratore passa `config["tickers"]` a ogni scraper
- **Venv obbligatorio**: dipendenze in venv (PEP 668, Arch)
- **Fail-closed (consolidator)**: un modulo fallito NON sparisce — compare con `status: "error"`; `signal_reliability: "low"` se ci sono errori o 0 sorgenti (mai "high" con sistema down)
- **Separazione semantica**: coverage ≠ availability ≠ usable_in_strategy_score; un proxy non entra mai nello score senza `proxy_accepted` esplicito
- **Priorità dati**: scraping (fresh) > manual override (valido+fresco) > missing/error
- **Segnale conforme alla strategia buy-the-dip**: la debolezza tecnica (sotto SMA, drawdown profondo) è profilo WATCHLIST, MAI sell — vendere richiede trigger di uscita (take-profit, deterioramento fondamentale, time-stop) non calcolabili dai dati tecnici
- **Gate FGI nella sintesi**: in greed (FGI≥56, per bande strategia F1) nessun COMPRA (non inseguire mercato caldo)

## Security Requirements
- Rate limiting e User-Agent browser per ogni richiesta (evita blocchi HTTP 418/403)
- **Rate limiting concreto**: `request_delay` (default 1.0s) tra i fetch dei ticker in `ohlcv_fetcher` — previene HTTP 429 di Yahoo
- Timeout con retry e backoff su ogni fetch
- Rispetto di robots.txt e termini d'uso dei siti
- Nessun secret hardcoded: uso di variabili d'ambiente
- **Nota yfinance**: i moduli basati su libreria (yfinance) non richiedono UA browser manuale — la libreria lo gestisce; il rate limiting resta comunque rilevante per evitare blocchi IP
- **Manual override**: nessun dato manuale viene mai confuso con dati scrapati (origin esplicito); validazione schema prima dell'uso

## 📂 Codebase References
**Fetch Utils**: `src/fetch_utils.py` — fallback generico (`fetch_first_success` + `try_parsers`); usato da FGI (catena 3 sorgenti) e AAII (2 parser); il vincitore è registrato nel campo `source` e mostrato nelle card del report HTML
**Indicator Registry**: `src/indicator_registry.py` + `indicator_registry.yaml` — matrice indicatori; `build_availability()` mappa output_key→stato runtime; `usable_for()` applica fail-closed sui proxy
**Manual Overrides**: `src/manual_overrides.py` + `manual_overrides.yaml` — `load_validated_overrides()`, `apply_overrides()` (priorità scraping>manual>missing), `is_fresh()` (scadenza)
**Scraper FGI**: `src/scrapers/fgi_scraper.py` — catena fallback CNN → feargreedmeter → feargreedindex, header browser, retry; validatore content-aware (rifiuta body senza "Stock Market")
**Scraper AAII**: `src/scrapers/aaii_scraper.py` — html_bars primario, dataChart5 legacy (rimosso da AAII)
**Scraper VIX**: `src/scrapers/vix_scraper.py` — VIX spot da CSV CBOE (scope cambiato da term structure; proxy dichiarato)
**Scraper OHLCV**: `src/scrapers/ohlcv_fetcher.py` — yfinance → cache su disco, multi_level_index=False, request_delay
**Scraper Indicators**: `src/scrapers/indicators.py` — legge cache, normalizza TitleCase, calcola con `ta`
**Scraper PCR**: `src/scrapers/pcr_scraper.py` — Equity PCR da CBOE (JSON escapato), Barchart sostituito (WAF 404)
**Scraper PCT SMA**: `src/scrapers/pct_sma_scraper.py` — breadth settoriale % sopra SMA50/200 da OHLCV locale (proxy dichiarato)
**Scraper Insider**: `src/scrapers/insider_scraper.py` — bonus H5 da OpenInsider (HTTP, solo acquisti)
**Report HTML**: `src/report_html.py` — pagina statica da output.json (dark+light, semafori, segnale con gate FGI, matrice indicatori con badge coverage/availability/usable/source, badge manual sugli override); aggiornare ad ogni nuovo scraper
**Orchestratore**: `src/orchestrator.py` — `run(config_path, output_path, db_path)`, crea `output/` automaticamente, inietta tickers e risolve cache_path, applica manual overrides, arricchisce matrice con source runtime
**Scheduler**: `src/scheduler.py` — `next_run`/`seconds_until` (funzioni pure, testabili senza rete), `run_once`, `run_loop`, CLI (`--once` o loop); legge `scheduler:` da config.yaml (interval/run_at/weekday)
**Moduli**: `src/config_loader.py` (validazione incl. `_validate_tickers`), `src/registry.py`, `src/consolidator.py` (fail-closed), `src/audit.py`
**Config**: `config.yaml` — chi/quando/dove + path output configurabili + sezione `tickers` + request_delay + `strategy` (indicator_registry, proxy_accepted, manual_overrides, force_manual_overrides)
**Output**: `output/output.json` (JSON consolidato + strategy_indicators), `output/scraper_audit.db` (SQLite audit), `output/report.html` (pagina statica)
**Strategia**: `/home/fibbione/Temp/strategia_trading/strategia_trading.md` + `specifiche_strategia.md` — regole buy-the-dip (Regola 0-4, matrice R/O) che guidano compute_signal

## Related Files
- navigation.md (indice del project intelligence)
- scraping-patterns.md (pattern scraper per modulo)
- report-html.md (pattern report HTML + segnale)
- aaii-scraping-guide.md (guida dettagliata pattern AAII)
