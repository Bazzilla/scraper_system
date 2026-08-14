# Design: Modulo pct_sma_scraper (breadth % sopra SMA50/SMA200)

**Data**: 2026-08-12
**Stato**: Approvato
**Scope**: Nuovo modulo che calcola la percentuale di ticker sopra SMA50/SMA200 (breadth settoriale) dai dati OHLCV locali

## Obiettivo

Creare `src/scrapers/pct_sma_scraper.py` che legge `output/ohlcv_cache.json`
(scritto da `ohlcv_fetcher`) e calcola per ogni categoria e totale la % di ticker
con `last_close >= SMA50` e `last_close >= SMA200`. È la breadth settoriale
della strategia buy-the-dip (indicatori supplementari #13-14):
- `% stocks above SMA 50`: **< 20% = ipervenduto diffuso**
- `% stocks above SMA 200`: **< 30% = mercato deteriorato**

## Scelta di sourcing (decisione)

La fonte originale `IndexIndicators.com` espone il dato **solo come immagine PNG**
del grafico — non parsabile. Barchart (WAF 404) e StockCharts (404) non sono
alternative valide. Decisione: **calcolo locale dai dati OHLCV** già scaricati
per il nostro universo ticker (breadth settoriale, non S&P 500 intero — più
coerente con la strategia che monitora i settori semi+difesa).

## Architettura

```
config.yaml (tickers: ~29) → ohlcv_fetcher → output/ohlcv_cache.json
                                              ↓
                              pct_sma_scraper → calcola % sopra SMA50/SMA200
                                              ↓
                              output: pct_sma (per categoria + totale)
```

Seguo il pattern di `indicators.py` (legge cache → calcola), NON uno scraper
di rete. Le SMA50/SMA200 vengono **ricalcolate dai record OHLCV** della cache
(come fa indicators.py con `ta`).

## Universo ticker ampliato (~29)

**Semiconduttori (19)**: AMAT, LRCX, KLAC, AVGO, ASML, TSM, AMD, MU, ADI, QCOM,
MRVL, ENTG + **NVDA, INTC, TXN, SWKS, MPWR, ON, NXPI**
**Difesa (10)**: RTX, LMT, NOC, GD, LHX + **AXON, HWM, HEI, TDG, TXT**

Totale: 29 ticker (12+7 semi, 5+5 difesa). Ampliamento in `config.yaml`.

## Logica di calcolo

Per ogni ticker con dati in cache:
1. Converti i record OHLCV in DataFrame (pattern `records_to_frame` di indicators.py)
2. Calcola SMA50 e SMA200 (`ta.trend.SMAIndicator`)
3. `above_sma50 = last_close >= sma50` (ultimo valore, se non-None)
4. `above_sma200 = last_close >= sma200` (idem)
5. Aggrega per categoria e totale: `above`, `total`, `pct = above/total*100`

Ticker senza dati sufficienti (es. < 50 record) → esclusi dal denominatore.
Isolamento per-ticker: un ticker con dati mancanti non blocca gli altri.

## Output (formato file.json)

```json
"pct_sma": {
  "semiconductors": { "above_sma50": 12, "total": 19, "pct_sma50": 63.2,
                      "above_sma200": 16, "pct_sma200": 84.2 },
  "defense": { "above_sma50": 8, "total": 10, "pct_sma50": 80.0,
               "above_sma200": 9, "pct_sma200": 90.0 },
  "total": { "above_sma50": 20, "total": 29, "pct_sma50": 69.0,
             "above_sma200": 25, "pct_sma200": 86.2 },
  "fetched_at": "...", "frequency": "daily", "stale_after_hours": 24, "status": "fresh"
}
```

## Semaforo nel report (soglie strategia #13-14)

| Metrica | Soglie | Classe |
|---------|--------|--------|
| pct_sma50 | <20% / 20-50% / >50% | fear / warning / ok |
| pct_sma200 | <30% / 30-60% / >60% | fear / warning / ok |

Card "Breadth settoriale" nel report con la % totale sopra SMA50/SMA200.

## Config.yaml

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

## File

```
src/scrapers/pct_sma_scraper.py
src/tests/test_pct_sma_scraper.py
config.yaml (ampliamento tickers + sezione pct_sma)
src/report_html.py (card breadth + legenda)
src/tests/test_report_html.py (test card)
```

## Manutenibilità strategia

`pct_sma` **non entra in compute_signal** (come PCR — è conferma macro
indipendente). Annotare nel ledger: se in futuro la strategia volesse usare la
breadth nello scoring, andrebbe aggiunta con la stessa logica del gate FGI.

## Fuori scope

- Breadth S&P 500 completo (richiederebbe download massivo di 500 ticker)
- Modifiche a compute_signal
- Scheduler
