# Storico del progetto

Questo file raccoglie le **decisioni e i fatti passati** del progetto: fonti
non più raggiungibili, cambi di scope, note di audit e roadmap completata.
Il README descrive solo lo **stato attuale**; qui vive la storia.

---

## Fonti escluse e motivi

### NAAIM Exposure Index — a pagamento

`naaim_scraper.py` è stato escluso: NAAIM ora è a pagamento e i dati pubblici
hanno 3 mesi di ritardo. L'indicatore è previsto dalla strategia (F3/#9) ed è
alimentabile manualmente via `manual_overrides.yaml`.

### VIX term structure (M1/M2) — non scrapabile

`vix_term_scraper.py` è stato escluso: VIX Central/VolChart espone un gate di
sessione Flask non riproducibile con `requests`. **Scope cambiato**: il modulo
attivo è `vix_scraper.py` che fornisce il VIX spot via CBOE (proxy, non
l'indicatore F3/10 della strategia). La term structure è alimentabile
manualmente via `manual_overrides.yaml` (M1/M2 leggibili da
https://vixcentral.com/).

### % sopra SMA50/SMA200 del mercato USA — non scrapabile

`pct_sma_scraper.py` è stato escluso: IndexIndicators espone solo PNG (non
scrapabile). Il proxy locale sui 29 ticker è stato **rimosso (2026-08-17)**;
l'indicatore si alimenta manualmente via `manual_overrides.yaml`
(pct_sma50/pct_sma200) con i valori del mercato USA.

### NYSE New Highs/New Lows — non implementato

`nh_nl_scraper.py` (indicatore #12 della strategia) non è mai stato
implementato: Barchart (WAF 404) e StockCharts (404) non sono scrapabili con
`requests`; nessuna altra fonte gratuita equivalente trovata. Il segnale
NH-NL resta da valutare manualmente.

---

## Gap semantici dichiarati (audit 2026-08-14)

Rispetto a `specifiche_strategia.md`:

- **VIX spot ≠ VIX Term Structure (F3/10)**: la strategia chiede la
  *backwardation* M1>M2 (panico a breve); il modulo fornisce il *livello* VIX
  spot. Sono indicatori diversi: il report etichetta la card "VIX Spot" per
  non confonderli.
- **Breadth di mercato (F3/13-14)**: le soglie della strategia (<20% SMA50,
  <30% SMA200) si riferiscono a *tutto il mercato USA*. IndexIndicators
  espone solo PNG (non scrapabile); il proxy locale sui 29 ticker è stato
  **rimosso (2026-08-17)** e l'indicatore si alimenta **manualmente** via
  `manual_overrides.yaml` (pct_sma50/pct_sma200) con i valori del mercato USA.
- **AAII**: fonte unica ufficiale (nessuna alternativa gratuita equivalente);
  `dataChart5` è stato rimosso da AAII (2026-08-14) → il parser attivo è
  `html_bars` (in versione precedente la fonte primaria dichiarata era
  `data_chart`, ora fallback legacy).

---

## Note di audit sui moduli

### AAII (2026-08-14)

- `dataChart5` rimosso da AAII → `html_bars` è diventata la strategia
  primaria; `data_chart` resta come fallback legacy.
- Blocco Cloudflare temporaneo (challenge `cf-chl`) verificato nella stessa
  giornata; fail-closed a runtime se il blocco si ripresenta.

### VIX (cambio di scope)

Scope cambiato da term structure (VIX Central non scrapabile) a VIX spot via
CBOE — il modulo è un **proxy**, non l'indicatore F3/10 della strategia.

### PCR (sostituzione fonte)

Equity PCR da CBOE; Barchart è stato sostituito (WAF 404).

### Insider (fallback protocollo)

Bonus H5 da OpenInsider: HTTPS non risponde → fallback su HTTP.

---

## Roadmap completata

- [x] Creare `pcr_scraper.py` (Equity PCR da CBOE)
- [x] Creare `ohlcv_fetcher.py` (yfinance) e `indicators.py` (ta)
- [x] Integrare uno scheduler (`src/scheduler.py` — loop/`--once`, sezione
      `scheduler:` in config)
- [x] Aggiungere fallback per fonti instabili (FGI: catena 3 sorgenti, AAII:
      try_parsers, `fetch_utils.py`)
- [x] Rimuovere il proxy `pct_sma` (breadth settoriale su 29 ticker) →
      `% sopra SMA50/200` del mercato USA alimentabile manualmente via
      `manual_overrides.yaml` (2026-08-17)