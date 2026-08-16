# scraper-system

Sistema **config-driven** per lo scraping di informazioni finanziarie da più fonti.
Un orchestratore legge un file di configurazione (chi scrapare, quando, dove sta lo script),
esegue gli scraper in sequenza, consolida i risultati in un unico JSON strutturato
e registra ogni esecuzione su un database SQLite di audit.

> **Nota**: questo README viene aggiornato man mano che il progetto evolve.

---

## Indice

- [Panoramica](#panoramica)
- [Struttura del progetto](#struttura-del-progetto)
- [Dove sono gli scraper](#dove-sono-gli-scraper)
- [Configurazione](#configurazione)
- [Comandi dell'orchestratore](#comandi-dellorchestratore)
- [Output](#output)
- [Come aggiungere un nuovo scraper](#come-aggiungere-un-nuovo-scraper)
- [Report HTML statico](#report-html-statico)
- [Test](#test)
- [Stato dei moduli](#stato-dei-moduli)

---

## Panoramica

```
config.yaml ──► config_loader ──► registry (import dinamico)
                    │                    │
                    ▼                    ▼
              orchestrator.run() ──► per-scraper: run(config)
                    │                    │
                    ▼                    ▼
              consolidator ──► output/output.json (formato file.json)
                    │
                    ▼
              audit ──► output/scraper_audit.db (SQLite)
```

**Flusso**: carica config → esegue ogni scraper in sequenza → consolida in un unico JSON
→ scrive audit log su SQLite → salva il JSON su disco. Un errore in un modulo **non blocca**
gli altri.

---

## Struttura del progetto

```
scraper-system/
├── config.yaml                  # Configurazione principale (chi/quando/dove)
├── requirements.txt             # Dipendenze riproducibili (pip install -r)
├── deploy/
│   └── systemd/                 # Unità systemd per esecuzione automatica (deploy)
│       ├── scraper-scheduler.service
│       └── scraper-scheduler.timer
├── docs/
│   ├── strategy/                # Strategia buy-the-dip (copia di riferimento nel progetto)
│   │   ├── strategia_trading.md
│   │   └── specifiche_strategia.md
│   └── superpowers/
│       ├── specs/2026-08-08-tickers-config-design.md
│       └── plans/2026-08-08-tickers-config.md
├── file.json                    # Formato di riferimento dell'output consolidato
├── README.md                    # Questo file
├── run.py                       # Un comando per tutto (orchestrazione + report)
├── .gitignore
├── output/                      # Cartella di output (creata automaticamente)
│   ├── output.json              #   JSON consolidato (formato file.json)
│   └── scraper_audit.db         #   Audit log SQLite
└── src/
    ├── orchestrator.py          # Orchestratore principale (entry point)
    ├── scheduler.py             # Scheduler (loop / --once, sezione scheduler in config)
    ├── config_loader.py         # Carica e valida config.yaml
    ├── registry.py              # Mappa nome → modulo scraper (import dinamico)
    ├── consolidator.py          # Costruisce il JSON di output (funzione pura)
    ├── audit.py                 # Audit log SQLite (cosa/quando/esito)
    ├── report_html.py              # Genera pagina HTML statica (output/report.html)
    ├── scrapers/                # ★ I moduli scraper vivono qui
    │   ├── fgi_scraper.py       #   CNN Fear & Greed Index
    │   ├── aaii_scraper.py      #   AAII Sentiment Survey
    │   ├── vix_scraper.py       #   VIX spot (CBOE)
    │   ├── pcr_scraper.py       #   Equity Put/Call Ratio (CBOE)
    │   ├── ohlcv_fetcher.py     #   OHLCV Yahoo (yfinance)
    │   ├── indicators.py        #   Indicatori tecnici (ta)
    │   ├── pct_sma_scraper.py   #   % sopra SMA50/SMA200 da OHLCV locale
    │   └── insider_scraper.py   #   Bonus insider (acquisti dirigenti/CEO/CFO)
    └── tests/                   # Test unitari
        ├── test_fgi_scraper.py
        ├── test_aaii_scraper.py
        ├── test_vix_scraper.py
        ├── test_pcr_scraper.py
        ├── test_ohlcv_fetcher.py
        ├── test_indicators.py
        ├── test_insider_scraper.py
        └── test_orchestrator.py
```

---

## Dove sono gli scraper

Tutti i moduli scraper vivono in **`src/scrapers/`**. Ogni modulo segue lo stesso
contratto: una funzione `run(config: dict) -> dict` che ritorna un dict strutturato.

> **⚠️ Criterio di inclusione**: vengono eseguiti scraping **solo di fonti aggiornate
> e gratuite**. Le fonti che richiedono abbonamento o che espongono dati ritardati
> (es. NAAIM, ora a pagamento con 3 mesi di ritardo) vengono **escluse**.

| File | Fonte | Output | Frequenza |
|------|-------|--------|-----------|
| `fgi_scraper.py` | CNN Fear & Greed | score 0-100, zona | giornaliera |
| `aaii_scraper.py` | AAII | % bullish/bearish/neutral | settimanale (giovedì) |
| `vix_scraper.py` | CBOE | VIX spot (close) | giornaliera |
| `ohlcv_fetcher.py` | Yahoo (yfinance) | OHLCV per ticker (cache) | giornaliera |
| `indicators.py` | — | RSI, OBV, MFI, SMA50/200, drawdown | giornaliera |
| `pcr_scraper.py` | CBOE | Equity Put/Call Ratio | giornaliera (lag 1gg) |
| `pct_sma_scraper.py` | — (calcolo locale OHLCV) | % sopra SMA50/SMA200 per settore | giornaliera |
| `insider_scraper.py` | OpenInsider (HTTP) | Bonus insider (acquisti dirigenti/CEO/CFO) | giornaliera |

**Esclusi** (non gratuiti/aggiornati):
- `naaim_scraper.py` — NAAIM Exposure Index ora è a pagamento; i dati pubblici hanno 3 mesi di ritardo.
- `vix_term_scraper.py` — VIX term structure (M1/M2) da VIX Central/VolChart: non scrapabile (gate di sessione Flask non riproducibile con `requests`). **Scope cambiato** a VIX spot via CBOE.
- `nh_nl_scraper.py` — NYSE New Highs/New Lows (indicatore #12 della strategia): **non implementato**. Barchart (WAF 404) e StockCharts (404) non sono scrapabili con `requests`; nessuna altra fonte gratuita equivalente trovata. Il segnale NH-NL resta da valutare manualmente.

**⚠️ Gap semantici dichiarati** (rispetto a `specifiche_strategia.md`, verificati in audit 2026-08-14):
- **VIX spot ≠ VIX Term Structure (F3/10)**: la strategia chiede la *backwardation* M1>M2 (panico a breve); il modulo fornisce il *livello* VIX spot. Sono indicatori diversi: il report etichetta la card "VIX Spot" per non confonderli.
- **Breadth settoriale ≠ % Stocks above SMA del mercato USA (F3/13-14)**: le soglie della strategia (<20% SMA50, <30% SMA200) si riferiscono a *tutto il mercato*; il modulo calcola la breadth **solo sui 29 ticker dei 2 settori**. Il dato è un proxy settoriale, non l'indicatore di mercato originale (IndexIndicators espone solo PNG, non scrapabile).
- **AAII**: fonte unica ufficiale (nessuna alternativa gratuita equivalente); `dataChart5` è stato rimosso da AAII (2026-08-14) → il parser attivo è `html_bars` (in versione precedente la fonte primaria dichiarata era `data_chart`, ora fallback legacy).

**⚠️ Fail-closed**: un modulo che fallisce **non sparisce** dall'output: viene registrato con `status: "error"`, compare nel report con badge errore e abbassa `signal_reliability` a `low`. Un sistema con 0 sorgenti valide ha affidabilità `low`, mai `high`.

### Matrice indicatori strategia (`indicator_registry.yaml`)

Il progetto include una **matrice machine-readable** (`indicator_registry.yaml`, caricata da `src/indicator_registry.py`) che dichiara per ogni indicatore della strategia:

- `coverage` (**statico, dalle specifiche strategiche**): true = l'indicatore **appartiene alla strategia** (citato in `specifiche_strategia.md`). NON dipende dall'implementazione né dal runtime: resta true anche se non implementato, non scrapabile, rotto, disponibile solo manualmente o non usabile nello scoring. false = artefatto informativo NON strategico (es. VIX spot).
- `implementation_status` (**statico**): `implemented` (modulo con semantica equivalente) · `proxy` (dato diverso che approssima l'indicatore, o artefatto informativo) · `missing` (gap dichiarato) · `manual_supported` (nessuno scraper, ma supporto via `manual_overrides.yaml`).
- `semantic_coherent`: true/false — true solo se il dato misura esattamente l'indicatore della strategia
- `output_key`: la chiave runtime dell'orchestratore che fornisce il dato (assente per gli indicatori senza modulo)

Per ogni indicatore vengono calcolati **campi distinti** (visibili sia nel JSON strutturato `strategy_indicators` sia nel report HTML):

| Campo | Significato |
|-------|-------------|
| **`coverage`** | L'indicatore appartiene alla strategia (statico, dalle specifiche). Non cambia mai in base al runtime. |
| **`implementation_status`** | Stato implementativo nel progetto (statico): implemented / proxy / missing / manual_supported. |
| **`availability`** | Il dato è **davvero disponibile a runtime**: il modulo ha prodotto `status: "fresh"` oppure esiste un manual override valido e fresco. Dinamico. |
| **`usable_in_strategy_score`** | True **solo** se `coverage=true` E `availability=true` E `implementation_status` in (implemented, manual_supported), oppure proxy esplicitamente accettato in `strategy.proxy_accepted` E disponibile. Fail-closed. |
| **`source`** | Provenienza runtime: `scraped` \| `manual` \| `missing`. |

Fail-closed: `coverage=false` mai usabile · `missing` mai usabile · proxy mai senza consenso esplicito · non disponibile a runtime → non usabile.

Esempio: **NAAIM** è previsto dalla strategia (F3/#9) → `coverage: true`, `implementation_status: manual_supported`; se non c'è un override valido e fresco → `availability: false`, `usable_in_strategy_score: false`, `source: missing`.

Il motore di scoring (`compute_signal`) consuma **solo indicatori implemented per-ticker** e non usa mai un proxy come se fosse l'originale senza consenso esplicito.

### Manual overrides (`manual_overrides.yaml`)

Per indicatori macro fragili (AAII, FGI, NAAIM) è possibile inserire manualmente un valore quando la fonte non è scrapabile o è temporaneamente indisponibile.

**Priorità (fail-closed)**: `scraping (fresh) > manual override (valido + fresco) > missing/error`.

Regole:
- **Tracciabilità**: il dato manuale è sempre marcato `source: "manual"` + `origin: "manual"` + `entered_by` + `note` — mai confuso con uno scrapato.
- **Validità temporale**: scade dopo `stale_after_hours` da `fetched_at`. Un override scaduto diventa `status: "stale"` e non è mai usabile nello scoring.
- **Fail-closed**: override malformato → log + ignorato (non rompe il pipeline); senza scraping valido E senza override valido → `missing/error`.
- **Default**: se sia scraping che override sono validi, vince lo scraping. `strategy.force_manual_overrides` (es. `["aaii"]`) forza il manuale — **disabilitato di default**.
- **Semantica**: un override valido dà `availability: true` e, se l'indicatore è previsto dalla strategia (`coverage: true`) con `implementation_status: manual_supported`, anche `usable_in_strategy_score: true` (es. NAAIM, VIX Term Structure). Gli indicatori `missing` (senza supporto manuale) restano non usabili finché il registry non viene aggiornato.

Formato (vedi `manual_overrides.yaml`): campi comuni `fetched_at`, `stale_after_hours`, `entered_by`, `note`; campi specifici `aaii`→bullish/neutral/bearish, `fgi`→score/zone, `naaim`→exposure.

---

## Configurazione

Tutto è configurato in **`config.yaml`** (alla radice del progetto).

### Sezione `output` (dove salvare i risultati)

```yaml
output:
  json_path: output/output.json      # JSON consolidato
  db_path: output/scraper_audit.db  # SQLite audit log
```

I percorsi sono **configurabili** e relativi alla radice del progetto. La cartella
`output/` viene creata automaticamente se non esiste.

### Sezione `scrapers` (chi/quando/dove)

```yaml
scrapers:
  fgi:                              # nome logico dello scraper
    module: scrapers.fgi_scraper    # dove sta lo script (import dinamico)
    output_key: fgi                 # chiave nel JSON di output
    schedule: daily                 # frequenza: daily | weekly
    config:                         # override passati a run(config)
      sources:                      # catena fallback (primo che risponde vince)
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
        User-Agent: "Mozilla/5.0 ..."
```

- **`module`**: percorso Python del modulo (deve esporre `run(config)`).
- **`output_key`**: chiave sotto cui il risultato appare nel JSON consolidato.
- **`schedule`**: `daily` o `weekly` (usato dallo scheduler).
- **`config`**: dict opzionale passato a `run(config)` per override (sources/url, timeout, retry, headers).
- **`sources`** (FGI): lista ordinata di fonti — la prima che risponde vince e il suo `name` finisce nel campo `source` dell'output (pattern `fetch_utils.fetch_first_success`).

### Sezione `tickers` (lista titoli da monitorare)

Sezione **opzionale** che elenca i titoli per i moduli OHLCV/indicators,
raggruppati per categoria:

```yaml
tickers:
  semiconductors:
    - symbol: AMAT
      name: Applied Materials
  defense:
    - symbol: RTX
      name: RTX
```

- **Categoria** (es. `semiconductors`, `defense`): lista di ticker dello stesso settore.
- **`symbol`**: simbolo del ticker (obbligatorio, univoco a livello globale).
- **`name`**: nome dell'azienda (obbligatorio).

### Moduli `ohlcv_fetcher` e `indicators` (OHLCV + indicatori tecnici)

Questi moduli consumano la sezione `tickers:` (iniettata dall'orchestratore) per
scarare OHLCV da Yahoo Finance e calcolare indicatori tecnici. Il flusso è a
**cache intermedia su disco**: `ohlcv_fetcher` scrive `output/ohlcv_cache.json`,
`indicators` lo legge.

```yaml
scrapers:
  ohlcv:
    module: scrapers.ohlcv_fetcher
    output_key: ohlcv
    schedule: daily
    config:
      cache_path: output/ohlcv_cache.json   # dove salvare i dati OHLCV
      period: 1y                            # finestra dati (1d,5d,1mo,3mo,6mo,1y,2y,5y,max)
      interval: 1d                          # granularità (1m..3mo; intraday max 60 giorni)
      timeout: 20
      retries: 3
      backoff: 2.0
      request_delay: 1.0                    # ⭐ secondi di pausa TRA i ticker (rate limiting)
      stale_after_hours: 24

  indicators:
    module: scrapers.indicators
    output_key: indicators
    schedule: daily
    config:
      cache_path: output/ohlcv_cache.json   # stessa cache di ohlcv
      rsi_window: 14
      mfi_window: 14
      sma_fast: 50
      sma_slow: 200
      drawdown_window: 252                  # giorni (52 settimane)
      stale_after_hours: 24
```

- **`request_delay`**: secondi di attesa tra un ticker e il successivo. Previene il
  **rate limiting** della fonte (Yahoo risponde HTTP 429 se le richieste sono troppo
  ravvicinate). Con 29 ticker e delay `1.0`, il fetch richiede ~30s. Impostalo a `0`
  per disabilitare la pausa (sconsigliato su liste lunghe).
- **`cache_path`**: percorso del file cache condiviso. Viene risolto automaticamente
  rispetto alla radice del progetto dall'orchestratore.
- **Isolamento per-ticker**: se un ticker fallisce (rete, dati mancanti), gli altri
  vengono comunque elaborati; lo `status` del modulo diventa `stale`.
- L'orchestratore **inietta** `tickers` in entrambi i moduli (retrocompatibile:
  gli altri scraper lo ignorano).

---

## Comandi dell'orchestratore

> **⚠️ Ambiente**: le dipendenze (yfinance, pandas, ta) vivono nel **venv** del progetto
> (`.venv/`, Python 3.14 — il sistema è PEP 668, non si installa a livello globale).
> Usa sempre `.venv/bin/python` per eseguire l'orchestratore e i test.

L'orchestratore è in **`src/orchestrator.py`**. Eseguilo dalla cartella `src/`:

```bash
cd src
../.venv/bin/python -c "from orchestrator import run; run('../config.yaml')"
```

La funzione `run(config_path, output_path=None, db_path=None)`:

| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `config_path` | *(obbligatorio)* | Percorso del `config.yaml` |
| `output_path` | da `config.yaml` | Dove scrivere il JSON consolidato |
| `db_path` | da `config.yaml` | Dove scrivere il database SQLite |

Se `output_path`/`db_path` non vengono passati, l'orchestratore li legge da `config.yaml`
e crea automaticamente le cartelle necessarie.

### Scheduler (`scheduler.py`)

Esegue l'intera orchestrazione secondo la sezione `scheduler:` di `config.yaml`:

```yaml
scheduler:
  interval: daily          # daily | weekly
  run_at: "08:00"          # opzionale, default "00:00" (HH:MM)
  # weekday: 0             # opzionale (weekly), 0-6, default 0=lunedì
```

```bash
cd src
../.venv/bin/python scheduler.py --config ../config.yaml --once   # esecuzione singola ora
../.venv/bin/python scheduler.py --config ../config.yaml          # loop infinito
```

- **`--once`**: esegue subito una volta e termina (utile per cron/systemd).
- **Senza `--once`**: loop che calcola la prossima esecuzione (funzioni pure `next_run`/`seconds_until`), attende e poi esegue l'orchestratore completo.
- Il loop esegue **tutti** gli scraper configurati a ogni run (il campo `schedule` per-scraper è informativo; l'orchestratore gestisce i fallimenti per-modulo).
- Per l'integrazione con systemd/cron: usare `--once` con un timer, oppure il loop come servizio.

### Deploy (esecuzione automatica)

Setup consigliato: **bare metal** (venv + systemd), non container — è un tool single-user a carico bassissimo, la persistenza (`output/`) è più semplice su filesystem e lo scheduler è un processo semplice gestito da systemd. Il codice richiede Python ≥ 3.10 (verificato su 3.12 e 3.14).

```bash
# 1. Una tantum — clone + ambiente
cd ~
git clone git@github.com:<USER>/scraper_system.git
cd scraper_system
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Aggiornamenti
git pull
.venv/bin/pip install -r requirements.txt

# 3. Test manuale
cd src && ../.venv/bin/python scheduler.py --config ../config.yaml --once
```

**Esecuzione automatica daily con systemd** (unità già pronte in `deploy/systemd/`):

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/scraper-scheduler.service deploy/systemd/scraper-scheduler.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now scraper-scheduler.timer
loginctl enable-linger $USER    # esegue anche senza login
```

Verifica: `systemctl --user list-timers` · log: `journalctl --user -u scraper-scheduler.service`

⚠️ Adatta i percorsi `%h/scraper_system/...` nella unità se il clone sta in un'altra posizione. Il timer usa `Persistent=true`: se la macchina era spenta alle 08:00, l'esecuzione avviene al primo avvio successivo.

### Esempio con override espliciti

```bash
cd src
../.venv/bin/python -c "from orchestrator import run; run('../config.yaml', '/tmp/out.json', '/tmp/audit.db')"
```

### Un comando per tutto (`run.py`)

Dalla radice del progetto, `run.py` esegue l'intera pipeline in un colpo solo
(orchestrazione → `output/output.json` + report HTML → `output/report.html`):

```bash
./.venv/bin/python run.py                  # usa config.yaml
./.venv/bin/python run.py path/to/config   # config esplicita
```

Modalità senza scraping:

```bash
./.venv/bin/python run.py --report-only      # SOLO report HTML dall'output esistente
./.venv/bin/python run.py --override-only    # applica manual overrides all'output esistente
                                             # (senza scraping) e rigenera report
```

Alias comodi (fish):

```fish
function scraper-run
    /percorso/del/progetto/.venv/bin/python /percorso/del/progetto/run.py $argv
end

function scraper-report
    /percorso/del/progetto/.venv/bin/python /percorso/del/progetto/run.py --report-only $argv
end
```

### Immessione manuale di un valore (es. NAAIM)

Per indicare un valore a mano (quando lo scraping non è possibile o il dato
corrente non è disponibile):

1. **Apri `manual_overrides.yaml`** alla radice e aggiungi/scommenta la voce
   dell'indicatore (campi comuni: `fetched_at`, `stale_after_hours`,
   `entered_by`, `note`; campi specifici: `naaim` → `exposure`, `fgi` →
   `score`/`zone`, `aaii` → `bullish`/`neutral`/`bearish`,
   `vix_term_structure` → `m1`/`m2` — structure/pct/difference derivati
   automaticamente).
2. **Imposta `fetched_at` a ORA** (il dato scade dopo `stale_after_hours`).
3. Applica senza rilanciare gli scraper:

```bash
./.venv/bin/python run.py --override-only    # oppure: scraper-run --override-only
```

Il valore manuale compare nell'output come `source: manual`, `origin: manual`;
l'indicatore risulta `availability: true` e (se previsto dalla strategia con
supporto manuale, es. NAAIM, VIX Term Structure) `usable_in_strategy_score: true`.

Per la **VIX Term Structure**: i valori M1/M2 possono essere letti manualmente
da https://vixcentral.com/ (es. M1 = futures VIX 1 mese, M2 = futures VIX 2
mesi).

---

## Output

### JSON consolidato (`output/output.json`)

Formato definito in `file.json`. Ogni voce ha `fetched_at`, `frequency`,
`stale_after_hours`, `status`. In coda c'è un `stale_summary`.

```json
{
  "generated_at": "2026-08-07T20:05:41+00:00",
  "fgi": {
    "score": 63.6,
    "zone": "greed",
    "fetched_at": "2026-08-07T20:01:23+00:00",
    "frequency": "daily",
    "stale_after_hours": 24,
    "status": "fresh"
  },
  "ohlcv": {
    "semiconductors": {
      "AMAT": {
        "symbol": "AMAT",
        "name": "Applied Materials",
        "last_close": 548.87,
        "last_date": "2026-08-12",
        "fetched_at": "2026-08-12T14:30:06+00:00",
        "frequency": "daily",
        "stale_after_hours": 24,
        "status": "fresh"
      }
    },
    "status": "fresh"
  },
  "indicators": {
    "semiconductors": {
      "AMAT": {
        "rsi_14": 52.08,
        "obv": 356286653.0,
        "mfi_14": 34.97,
        "sma_50": 557.88,
        "sma_200": 385.3,
        "drawdown_52w": -24.08,
        "symbol": "AMAT",
        "name": "Applied Materials",
        "fetched_at": "2026-08-12T14:30:06+00:00",
        "frequency": "daily",
        "stale_after_hours": 24,
        "status": "fresh"
      }
    },
    "status": "fresh"
  },
  "stale_summary": {
    "total_sources": 3,
    "fresh": 3,
    "stale": 0,
    "stale_details": [],
    "signal_reliability": "high"
  }
}
```

I moduli `ohlcv` e `indicators` ritornano dict **annidati per categoria → ticker**.
Lo `status` a livello modulo (es. `"status": "fresh"` sotto `ohlcv`) alimenta lo
`stale_summary` del consolidator: ogni modulo conta come **una** sorgente.

### Audit log SQLite (`output/scraper_audit.db`)

Tabella `executions` — un record per ogni esecuzione di scraper:

| Colonna | Descrizione |
|---------|-------------|
| `id` | chiave primaria |
| `scraper` | nome dello scraper |
| `executed_at` | timestamp esecuzione |
| `status` | `success` / `error` |
| `error` | messaggio di errore (se fallito) |

---

## Come aggiungere un nuovo scraper

1. Crea `src/scrapers/<nome>_scraper.py` con una funzione `run(config) -> dict`.
2. Aggiungi la voce in `config.yaml` sotto `scrapers:` (module, output_key, schedule, config).
3. Aggiungi un test in `src/tests/test_<nome>_scraper.py`.
4. Esegui l'orchestratore per verificare.

**Pattern del modulo** (vedi `fgi_scraper.py`):

```python
def run(config: dict) -> dict:
    """Fetch + parse + return dict strutturato."""
    data = fetch(config["url"], config.get("timeout", 15))
    parsed = parse(data)
    return build_result(parsed, now_iso())
```

---

## Report HTML statico

Genera una pagina HTML statica (dark theme con toggle light) con l'output
consolidato: card per gli indicatori di mercato, tabelle per settore con
indicatori tecnici e semafori, date di ultimo aggiornamento.

```bash
cd src
../.venv/bin/python -c "from report_html import render; render('../config.yaml')"
```

Il file viene scritto in `output/report.html`. La funzione accetta un override:

```bash
../.venv/bin/python -c "from report_html import render; render('../config.yaml', '/tmp/report.html')"
```

> **⚠️ Manutenibilità**: quando aggiungi un nuovo scraper/modulo, **aggiorna
> `src/report_html.py`** (render_market_cards / _ticker_sections / render_ticker_table)
> per renderizzarlo nella pagina. Aggiungi anche un test in `test_report_html.py`.

---

## Test

Esegui tutti i test dalla cartella `src/` (usa il Python del venv):

```bash
cd src
../.venv/bin/python -m unittest discover -s tests -v
```

I test coprono funzioni pure (parse, consolidate, validate) e il flusso dell'orchestratore
con scraper mock (deterministici, senza chiamate di rete). I test di `ohlcv_fetcher` e
`indicators` usano DataFrame sintetici e mock di yfinance — nessuna richiesta di rete.

---

## Stato dei moduli

| Modulo | Stato | Note |
|--------|-------|------|
| `fgi_scraper.py` | ✅ Funzionante | Catena fallback CNN → feargreedmeter → feargreedindex (primo che risponde vince), `source` nell'output. Richiede header browser (CNN blocca User-Agent con HTTP 418). Validatore content-aware: rifiuta block page e body senza marker "Stock Market" (feargreedmeter pubblica anche un FGI crypto). |
| `aaii_scraper.py` | ✅ Funzionante | Legge bullish/bearish/neutral. **`html_bars` è la strategia primaria** (AAII ha rimosso `dataChart5`, verificato 2026-08-14); `data_chart` resta come fallback legacy. ⚠️ 2026-08-14: blocco Cloudflare temporaneo (challenge `cf-chl`) — verificato di nuovo raggiungibile nella stessa giornata. Fail-closed a runtime se il blocco si ripresenta. |
| `vix_scraper.py` | ✅ Funzionante | VIX spot (close) da CSV ufficiale CBOE. Scope cambiato da term structure (VIX Central non scrapabile) — **proxy, non l'indicatore F3/10 della strategia**. |
| `ohlcv_fetcher.py` | ✅ Funzionante | OHLCV da Yahoo via yfinance, cache su disco. Rate limiting via `request_delay` (HTTP 429 evitato). |
| `indicators.py` | ✅ Funzionante | RSI/OBV/MFI/SMA50/200/drawdown con libreria ta (pandas-ta escluso: numba incompatibile Python 3.14). |
| Orchestratore | ✅ Funzionante | Config, isolamento errori, audit SQLite. Inietta `tickers` + risolve `cache_path`. **Fail-closed**: i moduli falliti compaiono con `status: "error"` nell'output. |
| Config `tickers` | ✅ Funzionante | 29 ticker in 2 categorie (semiconductors, defense), validato da `config_loader` |
| Moduli OHLCV/indicators | ✅ Smoke test OK | Orchestrazione end-to-end con rete reale: 5/5 fresh, 17/17 ticker con dati e indicatori. |
| `pcr_scraper.py` | ✅ Funzionante | Equity PCR da CBOE (Barchart sostituito: WAF 404). Soglia >0.80 fear. |
| `pct_sma_scraper.py` | ✅ Funzionante | Breadth **settoriale** da OHLCV locale (IndexIndicators: solo PNG, non scrapabile) — **proxy, non l'indicatore di mercato F3/13-14**. |
| `insider_scraper.py` | ✅ Funzionante | Bonus H5 da OpenInsider (HTTPS non risponde → HTTP) |
| NAAIM | ⚠️ Manual override | A pagamento, dati pubblici ritardati di 3 mesi. `coverage: true` (previsto F3/#9), `implementation_status: manual_supported` — alimentabile via `manual_overrides.yaml`; senza override valido → `availability: false`, non usable. |
| VIX term structure | ⚠️ Manual override | VIX Central non scrapabile (gateway di sessione). `coverage: true` (F3/#10), `implementation_status: manual_supported` — M1/M2 inseribili via `manual_overrides.yaml` (leggibili da https://vixcentral.com/); senza override valido → `availability: false`, non usable. VIX spot resta un proxy informativo separato. |
| NYSE NH-NL | ❌ Non implementato | Barchart (WAF 404) e StockCharts (404) non scrapabili; nessuna fonte gratuita equivalente trovata. |

---

## Roadmap

- [x] Creare `pcr_scraper.py` (Equity PCR da CBOE)
- [x] Creare `pct_sma_scraper.py` (breadth settoriale da OHLCV locale)
- [x] Creare `insider_scraper.py` (bonus H5 da OpenInsider, HTTP)
- [x] Creare `ohlcv_fetcher.py` (yfinance) e `indicators.py` (ta)
- [x] Integrare uno scheduler (`src/scheduler.py` — loop/`--once`, sezione `scheduler:` in config)
- [x] Aggiungere fallback per fonti instabili (FGI: catena 3 sorgenti, AAII: try_parsers, `fetch_utils.py`)