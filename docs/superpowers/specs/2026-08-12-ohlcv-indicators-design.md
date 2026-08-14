# Design: Moduli OHLCV fetcher + Indicators

**Data**: 2026-08-12
**Stato**: Approvato
**Scope**: Fetch dati OHLCV per i ticker configurati + calcolo indicatori tecnici

## Obiettivo

Implementare `ohlcv_fetcher.py` e `indicators.py`, i due moduli che consumano la
sezione `tickers:` di `config.yaml` (17 ticker in 2 categorie: semiconductors 12,
defense 5). `ohlcv_fetcher` scarica dati OHLCV da Yahoo Finance (yfinance) per ogni
ticker; `indicators` calcola indicatori tecnici (RSI, OBV, MFI, SMA50, SMA200,
drawdown 52w) usando la libreria `ta`.

## Dipendenze e ambiente

- **Python 3.14.6** (sistema Arch, PEP 668 externally-managed → serve **venv**).
- Pacchetti da installare nel venv: `yfinance` (1.5.2), `pandas` (3.0.5), `ta` (0.11.0).
- **`pandas-ta` è ESCLUSO**: dipende da `numba` che non supporta Python 3.14
  (`only versions >=3.10,<3.14 are supported`). Sostituito da `ta` 0.11.0.
- Libreria `ta` API (verificata su Context7):
  - `RSIIndicator(close, window=14).rsi()`
  - `SMAIndicator(close, window).sma_indicator()`
  - `ta.volume.money_flow_index(high, low, close, volume, window=14)`
  - OBV: `ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()`

## Architettura e flusso dati

```
config.yaml (tickers:) → ohlcv_fetcher.py → cache OHLCV su disco (output/ohlcv_cache.json)
                                             ↓
                                      indicators.py → indicatori per ticker
                                             ↓
                              consolidator → output/output.json
```

- Entrambi i moduli seguono il contratto `run(config) -> dict` del progetto.
- **Funzioni pure** per parse/serializzazione/calcolo (testabili senza rete).
- **DI per la rete** (pattern fgi/aaii/vix).

## Accesso ai tickers (iniezione orchestratore)

L'orchestratore passa a ogni scraper solo `scraper.get("config", {})` — i tickers
stanno nella sezione top-level. **Modifica minima retrocompatibile a orchestrator.py**:

```python
# orchestrator.py, dentro _run_scraper_safely o run()
scraper_config = dict(scraper.get("config", {}))
scraper_config["tickers"] = config.get("tickers", {})
result = run(scraper_config)
```

- I moduli esistenti (fgi, aaii, vix) ignorano `tickers` → nessun impatto.
- `ohlcv_fetcher` e `indicators` leggono `config["tickers"]`.
- Resta tutto config-driven, senza duplicare i ticker nel `config:` di ogni scraper.

## Cache OHLCV su disco

- `ohlcv_fetcher` scarica OHLCV per ogni ticker, serializza in `output/ohlcv_cache.json`
  (path configurabile via `config.cache_path`), e ritorna un risultato compatto per l'output.
- `indicators` legge il cache da disco, calcola gli indicatori, ritorna il dict per l'output.
- Il `cache_path` va risolto rispetto alla root del progetto (come `output_path`/`db_path`
  già fatti in orchestrator.py).
- Formato cache: JSON con struttura per categoria → ticker → lista record
  `{date, open, high, low, close, volume}` (ultimi ~250 giorni).

## Output JSON

```json
{
  "ohlcv": {
    "semiconductors": {
      "AMAT": { "symbol": "AMAT", "name": "Applied Materials", "last_close": 185.32,
                "last_date": "2026-08-11", "fetched_at": "...", "frequency": "daily",
                "stale_after_hours": 24, "status": "fresh" }
    },
    "status": "fresh"
  },
  "indicators": {
    "semiconductors": {
      "AMAT": { "rsi_14": 62.5, "obv": 123456, "mfi_14": 58.2,
                "sma_50": 180.1, "sma_200": 165.4, "drawdown_52w": -8.2,
                "fetched_at": "...", "frequency": "daily",
                "stale_after_hours": 24, "status": "fresh" }
    },
    "status": "fresh"
  }
}
```

Ogni voce mantiene i campi `fetched_at`/`frequency`/`stale_after_hours`/`status`
nel formato `file.json`.

**stale_summary (decisione: una sorgente per categoria)**: ogni modulo ritorna
il dict annidato per categoria/ticker **più** un campo `status` a livello top
del modulo, derivato dai ticker (fresh se tutti fresh, altrimenti stale). Il
consolidator esistente conta il modulo come una singola sorgente tramite quel
`status` top-level — nessuna modifica al consolidator. Ogni ticker mantiene il
proprio `status` interno per leggibilità.

## Config.yaml — due nuovi scraper

```yaml
scrapers:
  # ... fgi, aaii, vix esistenti ...
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

## Error handling e isolamento

- **Per-ticker**: un ticker che fallisce non blocca gli altri. L'errore va nel
  campo `error` del singolo ticker (o il ticker viene saltato con log).
- **Retry con backoff**: pattern `_fetch_with_retry` esistente.
- **Cache assente/corrotta**: `indicators` solleva errore pulito se il cache non
  esiste o è malformato → l'orchestratore lo registra come `error` nell'audit,
  senza bloccare gli altri moduli.

## Test

- **`ohlcv_fetcher`**: parse/serializzazione OHLCV con DataFrame mock (senza rete);
  merge categorie/ticker; formato cache.
- **`indicators`**: calcolo indicatori con dati sintetici noti (prezzi costanti →
  RSI/SMA noti); drawdown; cache assente → errore.
- **Orchestratore**: iniezione `tickers` retrocompatibile (i test mock esistenti
  restano verdi).

## File structure

```
src/scrapers/
├── ohlcv_fetcher.py     # fetch yfinance → cache su disco → dict output
└── indicators.py        # legge cache → calcola indicatori ta → dict output
src/tests/
├── test_ohlcv_fetcher.py
└── test_indicators.py
```

## Fuori scope

- Scheduler, alert, report.
- Moduli PCR, SMA (percent sopra SMA), Insider (piano separato).
- Persistenza storica degli indicatori nel tempo.