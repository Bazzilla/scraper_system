# Design: Report HTML statico (Market Dashboard)

**Data**: 2026-08-12
**Stato**: Approvato
**Scope**: Script standalone che genera una pagina HTML statica con l'output consolidato degli scraper

## Obiettivo

Creare `src/report_html.py`, uno script standalone che legge `output/output.json`
(l'output consolidato dell'orchestratore) e genera una pagina HTML statica
visivamente curata (dark theme con toggle light) con tutti i dati degli scraper:
indicatori di mercato (FGI, VIX, AAII), tabelle per settore (semiconduttori,
difesa) con indicatori tecnici e semafori, date di ultimo aggiornamento.

## File

```
src/report_html.py          # script standalone
src/tests/test_report_html.py
```

## Invocazione CLI

Dalla cartella `src/`:

```bash
../.venv/bin/python -c "from report_html import render; render('../config.yaml')"
```

- `render(config_path: str, output_path: str | None = None) -> str` — legge
  `config.yaml` per risolvere il path di `output.json` (default dal config
  `output.json_path`), genera `output/report.html`, ritorna il path del file
  generato.
- Se `output.json` non esiste → errore pulito (FileNotFoundError con messaggio).
- Script standalone — NON agganciato all'orchestratore (l'utente deciderà in futuro).

## Struttura pagina

```
┌─────────────────────────────────────────────┐
│  📊 Market Dashboard        [🌙/☀️ toggle]  │  header: generated_at + stale_summary badge
├─────────────────────────────────────────────┤
│  INDICATORI DI MERCATO                      │
│  ┌───────┐  ┌───────┐  ┌─────────────────┐  │
│  │ FGI   │  │ VIX   │  │ AAII (barre %)  │  │  card con valori + semafori
│  └───────┘  └───────┘  └─────────────────┘  │
├─────────────────────────────────────────────┤
│  SEMICONDUTTORI (12)                        │
│  ticker | last_close | RSI | MFI | OBV |   │  tabella con semafori
│  SMA50 | SMA200 | drawdown | aggiornato    │
├─────────────────────────────────────────────┤
│  DIFESA / AEROSPAZIO (5)                    │
│  (stessa tabella)                           │
├─────────────────────────────────────────────┤
│  footer: stale_summary dettagli             │
└─────────────────────────────────────────────┘
```

- **Header**: titolo, `generated_at` (formato leggibile), badge stato complessivo
  (fresh = verde / stale = rosso) basato su `stale_summary.signal_reliability` e `stale`.
- **Indicatori di mercato**: card per FGI (score + zona), VIX (close), AAII
  (barre % bullish/bearish/neutral). Mostrano anche `fetched_at` di ciascun modulo.
- **Tabelle ticker**: una sezione per categoria (semiconduttori, defense), con
  header "CATEGORIA (N ticker)". Colonne: Ticker, Nome, Last Close, RSI, MFI,
  OBV, SMA50, SMA200, Drawdown, Aggiornato.
- **Footer**: dettaglio `stale_summary` (total_sources, fresh, stale,
  stale_details se presenti).

## Semafori/colori

| Metrica | Soglie | Classe CSS / colore |
|---------|--------|---------------------|
| **FGI score** | 0-25 extreme_fear, 25-45 fear, 45-55 neutral, 55-75 greed, 75-100 extreme_greed | gradiente rosso → verde |
| **RSI** | > 70 overbought, < 30 oversold, altrimenti neutral | rosso / verde / neutro |
| **MFI** | > 80 overbought, < 20 oversold, altrimenti neutral | rosso / verde / neutro |
| **Drawdown** | >= -5 ok, -5..-15 warning, < -15 critical | verde / giallo / rosso |
| **Stale status** | fresh / stale | verde / rosso |

Ogni cella mostra **sempre il valore numerico** + badge/bordo colorato. I valori
`null`/`None` (es. SMA200 con dati insufficienti) mostrano "—" senza semaforo.

## Implementazione

- **Funzioni pure** per la costruzione delle sezioni HTML, testabili senza rete:
  - `render_market_cards(data) -> str`
  - `render_ticker_table(category, entries) -> str`
  - `semaphore_class(value, metric) -> str`
  - `render_stale_summary(summary) -> str`
  - `build_page(data) -> str` (assembla il documento completo)
- **CSS inline** nel template (nessuna dipendenza esterna) — pagina self-contained,
  funziona offline.
- **Toggle dark/light**: piccolo `<script>` inline che alterna una classe CSS
  sul `<body>`, persistito in `localStorage`. Default: dark.
- **Date**: `generated_at` e `fetched_at` formattate in locale leggibile
  (es. "12 ago 2026, 14:30").
- **Manutenibilità**: il design e il README devono ricordare che **aggiungendo un
  nuovo scraper/modulo va aggiornato `report_html.py`** per renderizzarlo.

## Test

- Render con output mock: la pagina contiene titolo, `generated_at`, sezioni
  (indicatori, categorie ticker), valori dei moduli, toggle, CSS inline.
- Semafori: RSI 75 → classe `overbought`; drawdown -20 → classe `critical`;
  FGI 63 → zona `greed`.
- Valori None → "—".
- `output.json` mancante → errore pulito.
- Date formattate correttamente.

## Documentazione

- **README.md**: nuova sezione "Report HTML statico" con comando d'uso e nota
  manutenibilità ("aggiungi uno scraper → aggiorna report_html.py").
- **`.opencode/context/project-intelligence/technical-domain.md`**: aggiunta a
  Codebase References con path e scopo.

## Fuori scope

- Hook nell'orchestratore (decisione futura dell'utente).
- Grafici interattivi / librerie JS esterne.
- Refresh automatico o live data.

## Estensione 2026-08-12: header centrato + legenda interattiva

- **Header tabella centrato**: `th { text-align: center }` — la testata centrata rende
  evidente che colonne come DRAWDOWN contengono due sotto-colonne (valore + badge).
- **Legenda indicatori** in fondo alla pagina (dopo il footer stale_summary), in due
  gruppi: "Indicatori di mercato" (FGI, VIX, AAII) e "Indicatori azionari" (RSI, MFI,
  OBV, SMA50/SMA200, Drawdown), più una sezione "Semafori" che spiega i colori
  (verde ok/oversold, giallo warning, rosso critical/overbought, blu neutral).
- **Toggle per riga**: ogni voce della legenda è un `<details>/<summary>` HTML nativo —
  click su "ℹ️" espande/chiude la spiegazione dettagliata in italiano (significato
  dell'indice + come contribuisce all'analisi).
- **Guida operativa finale**: sezione che spiega in quali casi un titolo potrebbe essere
  comprato (convergenza di segnali di ipervenduto + inversione) o venduto se detenuto
  in profitto (segnali di ipercomprato/indebolimento), con disclaimer. Non è consulenza
  finanziaria.

## Estensione 2026-08-12 (2): colonna Segnale + gate di mercato

- **Colonna "Segnale"** in ogni tabella ticker: `compute_signal(entry, regime)` produce
  COMPRA / VENDI / ATTENDI con badge colorato (🟢/🔴/⚪). Scoring: ±1 per RSI
  (<30/>70), MFI (<20/>80), prezzo vs SMA50, prezzo vs SMA200, drawdown (≥-5/<-15);
  soglie ≥+2 COMPRA, ≤-2 VENDI, altrimenti ATTENDI.
- **Gate di mercato (FGI)**: `market_regime(fgi_score)` → greed (≥55), fear (≤45),
  neutral. In **greed nessun COMPRA** (declassato ad ATTENDI — non inseguire un mercato
  caldo); in **fear nessun VENDI** (declassato ad ATTENDI — non vendere al minimo). I
  segnali estremi richiedono che clima e titolo puntino nella stessa direzione (strategia
  della Guida operativa).
- **Manutenibilità**: `compute_signal` e la sintesi del segnale vanno **aggiornati quando
  verranno implementati gli scraper rimanenti** (PCR, SMA percent, Insider) se i loro
  indicatori entrano nella strategia di trading — rileggere la Guida operativa e
  aggiornare scoring/gate di conseguenza.

## Correzione 2026-08-12: classe WATCHLIST al posto di VENDI

Analisi del caso QCOM contro `strategia_trading.md` / `specifiche_strategia.md`
(in `docs/strategy/`): il motore mappava la debolezza
tecnica (prezzo sotto SMA50/SMA200 + drawdown profondo) su "sell", ma la strategia
**non prevede SELL come classe di output** (solo ENTRA/MONITORA/WATCHLIST/LASCIA) e
la vendita è riservata ai trigger di uscita E1/E2/E3 (take-profit, deterioramento
fondamentale, time-stop) — che il dashboard non può calcolare. Inoltre E2 è esplicita:
"stop-loss SOLO su deterioramento fondamentale, MAI su prezzo".

**Patch applicata**:
- `score <= -2` → **`watchlist`** (debolezza profonda = profilo buy-the-dip, MAI sell)
- Gate: `greed` blocca `buy`; `fear` mantiene `watchlist`
- **`sell` rimosso dal motore** — un VENDI richiede dati fondamentali/posizione assenti
- Badge: COMPRA / WATCHLIST / ATTENDI (🟢/🟠/⚪)
- Test di regressione: `test_qcom_case_is_watchlist_not_sell` (QCOM con FGI 62.66 greed
  e dati reali → WATCHLIST, non sell)