<!-- Context: project-intelligence/navigation | Priority: critical | Version: 1.15 | Updated: 2026-08-17 -->

# Project Intelligence

## Quick Routes
| File | Description | Priority |
|------|-------------|----------|
| technical-domain.md | Tech stack, architettura, naming, standard, security, strategy registry & manual override | critical |
| scraping-patterns.md | Pattern scraper per modulo (FGI, VIX, AAII, OHLCV, Indicators, PCR, PCT SMA, Insider, config) | high |
| report-html.md | Pattern report HTML + segnale COMPRA/WATCHLIST/ATTENDI con gate FGI | high |
| aaii-scraping-guide.md | Guida dettagliata scraping AAII (selectors, fallback, strategia) | high |

## Deep Dives
- **aaii-scraping-guide.md** → dettaglio completo del pattern AAII citato in scraping-patterns.md
- **scraping-patterns.md** → dettaglio completo dei pattern scraper citati in technical-domain.md
- **report-html.md** → dettaglio completo del pattern report/segnale citato in technical-domain.md

## Update Log
- **2026-08-07**: Creato technical-domain.md v1.0 (wizard /add-context)
- **2026-08-07**: Aggiornato technical-domain.md v1.1 — orchestratore, path output configurabili, API CNN FGI, header browser
- **2026-08-07**: Aggiornato technical-domain.md v1.2 — pattern VIX spot (CBOE, scope cambiato da term structure), pattern AAII (fallback HTML bars), codebase refs aggiornati
- **2026-08-07**: Harvestato aaii-scraping-guide.md v1.0 (da .tmp/external-context); rimosso vixcentral obsoleto
- **2026-08-12**: Aggiornato technical-domain.md v1.3 — pandas-ta → ta 0.11.0 (numba/Python 3.14), venv/PEP 668, pattern sezione `tickers`, standard (isolamento per-ticker, iniezione tickers), nota security yfinance, refs OHLCV/indicators
- **2026-08-12**: Aggiornato technical-domain.md v1.4 — moduli OHLCV/indicators operativi, pattern report_html (segnale COMPRA/WATCHLIST/ATTENDI con gate FGI), request_delay (rate limiting), naming segnale, strategia buy-the-dip in `docs/strategy/`, standard segnale conforme alla strategia
- **2026-08-12**: Splittato technical-domain.md v1.5 (MVI compliance <200 righe) — creati scraping-patterns.md v1.0 (pattern scraper) e report-html.md v1.0 (pattern report/segnale); technical-domain.md ridotto a spina dorsale (stack, architettura, naming, standard, security)
- **2026-08-12**: scraping-patterns.md v1.1, technical-domain.md v1.6, navigation.md v1.4 — aggiunto pcr_scraper.py (Equity PCR da CBOE); spec/plan in docs/superpowers
- **2026-08-12**: scraping-patterns.md v1.2 — corretto pattern PCR (regex allineata al codice reale, fallback documentato)
- **2026-08-12**: pct_sma_scraper.py (breadth da OHLCV locale) — scraping-patterns.md v1.3, technical-domain.md v1.7, navigation.md v1.5
- **2026-08-12**: insider_scraper.py (bonus H5 da OpenInsider) — scraping-patterns.md v1.4, technical-domain.md v1.8, navigation.md v1.6
- **2026-08-14**: fetch_utils.py (fallback generico `fetch_first_success` + `try_parsers`) — FGI catena 3 sorgenti e AAII `source` nel report HTML — scraping-patterns.md v1.5, technical-domain.md v1.9, navigation.md v1.7
- **2026-08-14**: indicator_registry (coverage/availability/usable_in_strategy_score) + manual_overrides (scraping>manual>missing, validazione, scadenza, source=manual) + fail-closed consolidator + audit fallback-fonti — technical-domain.md v1.10, navigation.md v1.8
- **2026-08-14**: correzione semantica coverage (statico, dalle specifiche) + nuovo campo implementation_status (implemented/proxy/missing/manual_supported) + naaim manual_supported — technical-domain.md v1.11, navigation.md v1.9
- **2026-08-14**: scheduler.py (loop/--once, sezione scheduler in config.yaml, validazione config_loader) — chiude Roadmap — technical-domain.md v1.12, navigation.md v1.10
- **2026-08-14**: requirements.txt (dipendenze riproducibili) + deploy/systemd (service+timer daily) + verifica Python 3.12 e 3.14 (220 test OK) + repo GitHub — technical-domain.md v1.13, navigation.md v1.11
- **2026-08-15**: copia strategia in docs/strategy/ (autonomia del progetto, niente percorsi esterni) — technical-domain.md v1.14, navigation.md v1.12, report-html.md v1.1
- **2026-08-16**: VIX term structure → manual_supported (M1/M2 via manual_overrides, fonte vixcentral.com) — technical-domain.md v1.15, navigation.md v1.13
- **2026-08-16**: run.py 3 modalità (full/--report-only/--override-only), fix persisted manual non blocca override, aliases fish scraper-run/scraper-report — technical-domain.md v1.16, navigation.md v1.14
- **2026-08-17**: rimosso proxy pct_sma (breadth settoriale 29 ticker) → `% sopra SMA50/200` mercato USA manual_supported via manual_overrides.yaml — technical-domain.md v1.17, navigation.md v1.15, scraping-patterns.md v1.6