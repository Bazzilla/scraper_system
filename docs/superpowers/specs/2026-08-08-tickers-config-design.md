# Design: Configurazione ticker per settore

**Data**: 2026-08-08
**Stato**: Approvato
**Scope**: Solo OHLCV + indicatori (moduli futuri `ohlcv_fetcher.py` e `indicators.py`)

## Obiettivo

Aggiungere a `config.yaml` una sezione `tickers:` che elenca i titoli da monitorare,
raggruppati per categoria (settore), con simbolo e nome azienda. La sezione è la fonte
di verità per i moduli futuri che scaricano OHLCV (yfinance) e calcolano indicatori
tecnici (RSI, OBV, MFI, SMA50/200, drawdown).

## Struttura YAML

Sezione top-level `tickers:` in `config.yaml`, con categorie come liste di dict:

```yaml
tickers:
  semiconductors:
    - symbol: AMAT
      name: Applied Materials
    - symbol: LRCX
      name: Lam Research
    - symbol: KLAC
      name: KLA
    - symbol: AVGO
      name: Broadcom
    - symbol: ASML
      name: ASML Holding
    - symbol: TSM
      name: Taiwan Semiconductor
    - symbol: AMD
      name: Advanced Micro Devices
    - symbol: MU
      name: Micron
    - symbol: ADI
      name: Analog Devices
    - symbol: QCOM
      name: Qualcomm
    - symbol: MRVL
      name: Marvell
    - symbol: ENTG
      name: Entegris
  defense:
    - symbol: RTX
      name: RTX
    - symbol: LMT
      name: Lockheed Martin
    - symbol: NOC
      name: Northrop Grumman
    - symbol: GD
      name: General Dynamics
    - symbol: LHX
      name: L3Harris
```

Totale: 17 ticker (12 semiconduttori + 5 difesa/aerospazio).

## Regole di validazione (config_loader.py)

- Sezione `tickers` **opzionale** → esecuzioni senza ticker continuano a funzionare (retrocompatibilità).
- Ogni categoria è una lista **non vuota** di dict.
- Ogni voce richiede:
  - `symbol`: stringa, obbligatoria
  - `name`: stringa, obbligatoria
- **Symbol univoci** a livello globale (nessun duplicato tra categorie).

## Consumo da parte dei moduli futuri

- `ohlcv_fetcher.py` → legge `tickers`, itera categorie/ticker, scarica OHLCV per ciascuno via yfinance.
- `indicators.py` → usa gli stessi dati per calcolare RSI, OBV, MFI, SMA50/200, drawdown.
- L'output JSON conserverà la struttura annidata:
  - `ohlcv.semiconductors.AMAT {...}`
  - `indicators.semiconductors.AMAT {...}`

## Test

- Validazione config: config valida ✓, categoria vuota ✗, symbol mancante ✗, duplicato ✗, sezione assente (ok, opzionale).
- Aggiornamento dell'output JSON atteso nei test dell'orchestratore.

## Fuori scope

- Implementazione dei moduli `ohlcv_fetcher.py` e `indicators.py` (piano separato).
- Scheduler, alert, report.