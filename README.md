# scraper-system

Sistema **config-driven** per lo scraping di informazioni finanziarie da più fonti.
Un orchestratore legge un file di configurazione (chi scrapare, quando, dove sta lo script),
esegue gli scraper in sequenza, consolida i risultati in un unico JSON strutturato
e registra ogni esecuzione su un database SQLite di audit.

---

## Indice

- [Panoramica](#panoramica)
- [Struttura del progetto](#struttura-del-progetto)
- [Scraper](#scraper)
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
│   ├── history.md               # Storico: fonti escluse, audit, roadmap completata
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
    ├── report_html.py              # Orchestratore report (ri-esporta dai moduli)
    ├── report_helpers.py           #   Funzioni pure (semafori, format, badge)
    ├── report_cards.py             #   Card indicatori di mercato
    ├── report_tables.py            #   Tabelle ticker + matrice indicatori
    ├── report_legend.py            #   Legenda e guida
    ├── scrapers/                # ★ I moduli scraper vivono qui
    │   ├── fgi_scraper.py       #   CNN Fear & Greed Index
    │   ├── aaii_scraper.py      #   AAII Sentiment Survey
    │   ├── vix_scraper.py       #   VIX spot (CBOE)
    │   ├── pcr_scraper.py       #   Equity Put/Call Ratio (CBOE)
    │   ├── ohlcv_fetcher.py     #   OHLCV Yahoo (yfinance)
    │   ├── indicators.py        #   Indicatori tecnici (ta)
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

## Scraper

Tutti i moduli scraper vivono in **`src/scrapers/`**. Ogni modulo segue lo stesso
contratto: una funzione `run(config: dict) -> dict` che ritorna un dict strutturato.

> **⚠️ Criterio di inclusione**: vengono eseguiti scraping **solo di fonti aggiornate
> e gratuite**. Le fonti che richiedono abbonamento o che espongono dati ritardati
> vengono **escluse** (vedi `docs/history.md` per i motivi).

| File | Fonte | Output | Frequenza |
|------|-------|--------|-----------|
| `fgi_scraper.py` | CNN Fear & Greed | score 0-100, zona | giornaliera |
| `aaii_scraper.py` | AAII | % bullish/bearish/neutral | settimanale (giovedì) |
| `vix_scraper.py` | CBOE | VIX spot (close) | giornaliera |
| `ohlcv_fetcher.py` | Yahoo (yfinance) | OHLCV per ticker (cache) | giornaliera |
| `indicators.py` | — | RSI, OBV, MFI, SMA50/200, drawdown | giornaliera |
| `pcr_scraper.py` | CBOE | Equity Put/Call Ratio | giornaliera (lag 1gg) |
| `nh_nl_scraper.py` | Barchart (browser headers) | NYSE 52-week new highs/lows | giornaliera (end-of-day) |
| `insider_scraper.py` | OpenInsider (HTTP) | Bonus insider (acquisti dirigenti/CEO/CFO) | giornaliera |

**Non scrapabili → alimentabili manualmente** via `manual_overrides.yaml`:
NAAIM, VIX term structure (M1/M2), % sopra SMA50/200 del mercato USA.

**⚠️ Fail-closed**: un modulo che fallisce **non sparisce** dall'output: viene registrato
con `status: "error"`, compare nel report con badge errore e abbassa `signal_reliability`
a `low`. Un sistema con 0 sorgenti valide ha affidabilità `low`, mai `high`.

### Matrice indicatori strategia (`indicator_registry.yaml`)

Il progetto include una **matrice machine-readable** (`indicator_registry.yaml`, caricata
da `src/indicator_registry.py`) che dichiara per ogni indicatore della strategia:

- `coverage` (**statico**): true = l'indicatore **appartiene alla strategia** (citato in
  `specifiche_strategia.md`). Non dipende da implementazione né runtime.
- `implementation_status` (**statico**): `implemented` · `proxy` · `missing` ·
  `manual_supported`.
- `semantic_coherent`: true solo se il dato misura esattamente l'indicatore della strategia.
- `output_key`: la chiave runtime dell'orchestratore che fornisce il dato.

Per ogni indicatore vengono calcolati **campi distinti** (nel JSON `strategy_indicators`
e nel report HTML):

| Campo | Significato |
|-------|-------------|
| **`coverage`** | L'indicatore appartiene alla strategia (statico, dalle specifiche). |
| **`implementation_status`** | Stato implementativo nel progetto (statico). |
| **`availability`** | Il dato è **davvero disponibile a runtime**: modulo `status: "fresh"` oppure manual override valido e fresco. Dinamico. |
| **`usable_in_strategy_score`** | True **solo** se `coverage=true` E `availability=true` E `implementation_status` in (implemented, manual_supported), oppure proxy esplicitamente accettato in `strategy.proxy_accepted` E disponibile. Fail-closed. |
| **`source`** | Provenienza runtime: `scraped` \| `manual` \| `missing`. |

Fail-closed: `coverage=false` mai usabile · `missing` mai usabile · proxy mai senza consenso
esplicito · non disponibile a runtime → non usabile. Il motore di scoring (`compute_signal`)
consuma **solo indicatori implemented per-ticker** e non usa mai un proxy come se fosse
l'originale senza consenso esplicito.

### Manual overrides (`manual_overrides.yaml`)

Per indicatori macro fragili (AAII, FGI, NAAIM) è possibile inserire manualmente un valore
quando la fonte non è scrapabile o è temporaneamente indisponibile.

**Priorità (fail-closed)**: `scraping (fresh) > manual override (valido + fresco) > missing/error`.

Regole:
- **Tracciabilità**: il dato manuale è sempre marcato `source: "manual"` + `origin: "manual"`
  + `entered_by` + `note` — mai confuso con uno scrapato.
- **Validità temporale**: scade dopo `stale_after_hours` da `fetched_at`. Un override scaduto
  diventa `status: "stale"` e non è mai usabile nello scoring.
- **Fail-closed**: override malformato → log + ignorato (non rompe il pipeline); senza
  scraping valido E senza override valido → `missing/error`.
- **Default**: se sia scraping che override sono validi, vince lo scraping.
  `strategy.force_manual_overrides` (es. `["aaii"]`) forza il manuale — **disabilitato di default**.
- **Semantica**: un override valido dà `availability: true` e, se l'indicatore è previsto
  dalla strategia (`coverage: true`) con `implementation_status: manual_supported`, anche
  `usable_in_strategy_score: true` (es. NAAIM, VIX Term Structure).

Formato (vedi `manual_overrides.yaml`): campi comuni `fetched_at`, `stale_after_hours`,
`entered_by`, `note`; campi specifici `aaii`→bullish/neutral/bearish, `fgi`→score/zone,
`naaim`→exposure.

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
raggruppati per categoria. Ogni ticker può avere **metadata strategici**
(display-only nel report, mai usati come segnale):

```yaml
tickers:
  semiconductors:
    - symbol: AMAT
      name: Applied Materials
      quality_tier: core            # core | secondary | opportunistic
      strategy_role: semiconductor_equipment
      buy_the_dip_validity: high    # high | medium | low
      notes: "Nota opzionale"       # mostrata nel report
  defense:
    - symbol: RTX
      name: RTX
```

- **Categoria** (es. `semiconductors`, `defense`): lista di ticker dello stesso settore.
- **`symbol`**: simbolo del ticker (obbligatorio, univoco a livello globale).
- **`name`**: nome dell'azienda (obbligatorio).
- **Metadata** (opzionali): `quality_tier`, `strategy_role`, `buy_the_dip_validity`,
  `notes` — validati da `config_loader` e mostrati nel report sotto il nome del ticker.
  Formato legacy supportato: lista semplice di simboli (`["AMAT", "LRCX"]`).

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

Script eseguibili (`bin/`, risolvono i path dalla propria posizione — funzionano
da qualsiasi directory):

```bash
./bin/scraper-run                 # pipeline completa (scraping + report)
./bin/scraper-run --override-only # applica manual overrides senza scraping
./bin/scraper-report              # SOLO report HTML dall'output esistente
./bin/scraper-websrv              # mini-server locale (default porta 8900, solo localhost)
./bin/scraper-websrv -p 9000      # stessa cosa su altra porta
./bin/scraper-websrv --lan        # accessibile dagli altri dispositivi della LAN
```

Il server espone `/report.html` (dashboard), `/overrides.html` (immissione
manuale) e `/tickers.html` (editor liste ticker); la root `/` redirige alla
dashboard. **Tutte le pagine e le API richiedono Basic Auth** (default:
`admin` / `so€uri€€€`; personalizzabile creando un file `.server-auth`
git-ignored nella root con una riga `user:password`). Con `--lan` il bind è
su `0.0.0.0`: l'accesso è protetto dalle credenziali, ma resta consigliato
solo su rete fidata (le credenziali viaggiano in chiaro senza HTTPS).

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
./.venv/bin/python run.py --override-only    # oppure: ./bin/scraper-run --override-only
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
> i moduli report** (`report_cards.py` / `report_tables.py` / `report_legend.py`,
> ri-esportati da `report_html.py`) per renderizzarlo nella pagina. Aggiungi anche un test in `test_report_html.py`.

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
| `fgi_scraper.py` | ✅ Funzionante | Catena fallback CNN → feargreedmeter → feargreedindex (primo che risponde vince), `source` nell'output. Richiede header browser (CNN blocca User-Agent con HTTP 418). Validatore content-aware: rifiuta block page e body senza marker "Stock Market". |
| `aaii_scraper.py` | ✅ Funzionante | Legge bullish/bearish/neutral. Parser primario `html_bars`, fallback legacy `data_chart`. Fail-closed a runtime se la fonte blocca. |
| `vix_scraper.py` | ✅ Funzionante | VIX spot (close) da CSV ufficiale CBOE. **Proxy**, non l'indicatore F3/10 della strategia (term structure). |
| `ohlcv_fetcher.py` | ✅ Funzionante | OHLCV da Yahoo via yfinance, cache su disco. Rate limiting via `request_delay` (HTTP 429 evitato). |
| `indicators.py` | ✅ Funzionante | RSI/OBV/MFI/SMA50/200/drawdown con libreria ta (pandas-ta escluso: numba incompatibile Python 3.14). |
| Orchestratore | ✅ Funzionante | Config, isolamento errori, audit SQLite. Inietta `tickers` + risolve `cache_path`. **Fail-closed**: i moduli falliti compaiono con `status: "error"` nell'output. |
| Config `tickers` | ✅ Funzionante | 39 ticker in 2 categorie (semiconductors, defense) con metadata strategici, validato da `config_loader`. |
| `pcr_scraper.py` | ✅ Funzionante | Equity PCR da CBOE. Soglia >0.80 fear. |
| `nh_nl_scraper.py` | ✅ Funzionante | NYSE 52-week new highs/lows da Barchart (header browser; WAF 404 superato). Copia mobile duplicata skippata. `trade_date` end-of-day. |
| `insider_scraper.py` | ✅ Funzionante | Bonus H5 da OpenInsider (fallback HTTP). |
| NAAIM | ⚠️ Manual override | `coverage: true` (F3/#9), `implementation_status: manual_supported` — alimentabile via `manual_overrides.yaml`; senza override valido → `availability: false`, non usable. |
| VIX term structure | ⚠️ Manual override | `coverage: true` (F3/#10), `implementation_status: manual_supported` — M1/M2 inseribili via `manual_overrides.yaml` (leggibili da https://vixcentral.com/); senza override valido → `availability: false`, non usable. VIX spot resta un proxy informativo separato. |
| % sopra SMA 50/200 (mercato USA) | ⚠️ Manual override | `coverage: true` (F3/#13-14), `implementation_status: manual_supported` — pct_sma50/pct_sma200 inseribili via `manual_overrides.yaml` con i valori del mercato USA. |
| NYSE NH-NL | ✅ Funzionante | `coverage: true` (F3/#12), `implementation_status: implemented` — NYSE 52-week new highs/lows da Barchart (header browser, copia mobile skippata). |

---

Per lo **storico** del progetto (fonti escluse, note di audit, roadmap completata):
vedi [`docs/history.md`](docs/history.md).