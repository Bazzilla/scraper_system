# Specifica funzionalità: Portfolio, transazioni e strategia SELL

## 1. Obiettivo

Aggiungere al progetto `scraper_system` una nuova funzionalità per:

1. registrare gli acquisti e le vendite effettuate dall’utente;
2. calcolare automaticamente le posizioni attualmente aperte;
3. mostrare una pagina HTML dedicata al portafoglio;
4. valutare ogni posizione aperta secondo una strategia SELL coerente con la strategia Buy-the-Dip esistente;
5. suggerire azioni informative come:
   - `MANTIENI`
   - `PRENDI PROFITTO PARZIALE`
   - `RIDUCI ESPOSIZIONE`
   - `ATTENZIONE`
   - `NESSUNA POSIZIONE`

Il sistema **non deve emettere ordini operativi vincolanti**.  
Il report e la nuova pagina portfolio devono restare strumenti di supporto decisionale.

---

## 2. Principio fondamentale di sviluppo

Lo sviluppo deve procedere **a step sequenziali**.

Si passa allo step successivo **solo quando quello precedente è concluso, testato e verificato**.

Ogni step deve terminare con:

1. elenco dei file modificati;
2. diff sintetico;
3. test eseguiti;
4. conferma che le funzionalità precedenti non sono state rotte;
5. eventuali punti ambigui rimasti aperti.

È esplicitamente vietato mescolare più step nella stessa sessione se non strettamente necessario.

La priorità è:

```text
semplicità progettuale > completezza prematura
```

---

## 3. Contesto del progetto attuale

Il progetto attuale è un sistema config-driven per scraping finanziario e generazione report.

Componenti rilevanti già presenti:

- `config.yaml`
  - contiene scraper attivi;
  - contiene ticker monitorati;
  - contiene metadata strategici sui ticker.

- `run.py`
  - esegue pipeline completa;
  - genera `output/output.json`;
  - genera `output/report.html`.

- `src/orchestrator.py`
  - orchestra gli scraper.

- `src/consolidator.py`
  - consolida i risultati nel JSON finale.

- `src/report_html.py`
  - entrypoint del report HTML.

- `src/report_helpers.py`
  - contiene funzioni pure per segnali, badge e logica helper.

- `src/report_cards.py`
  - render delle card indicatori di mercato.

- `src/report_tables.py`
  - render delle tabelle ticker e indicatori.

- `src/report_legend.py`
  - legenda e spiegazioni report.

- `src/scrapers/ohlcv_fetcher.py`
  - scarica dati OHLCV da Yahoo/yfinance.

- `src/scrapers/indicators.py`
  - calcola RSI, OBV, MFI, SMA50, SMA200, drawdown 52w.

- `src/scrapers/valuation.py`
  - raccoglie fair value / target analyst / multipli.
  - Attualmente è in modalità validation/display-only.

- `src/scrapers/insider_scraper.py`
  - raccoglie acquisti insider.

- `manual_overrides.yaml`
  - consente override manuali per indicatori macro non scrapabili.

- `indicator_registry.yaml`
  - dichiara copertura, disponibilità e usabilità degli indicatori strategici.

- `output/output.json`
  - contiene dati consolidati dopo ogni run.

- `output/scraper_audit.db`
  - contiene audit tecnico delle esecuzioni scraper.

La nuova funzionalità portfolio deve integrarsi con questa architettura senza stravolgerla.

---

## 4. Vincoli strategici esistenti

La strategia BUY attuale è una strategia Buy-the-Dip.

Il gate operativo principale è il Fear & Greed Index:

```text
FGI mancante/stale → nessun ingresso
FGI > 40 → nessun ingresso
25 < FGI <= 40 → sola osservazione
FGI <= 25 → ingresso valutabile
FGI <= 20 → regime più forte, per ora senza label separata
```

La nuova strategia SELL deve essere separata dalla strategia BUY.

Non devono essere confuse queste due logiche:

```text
BUY strategy = quando valutare nuovi ingressi
SELL strategy = come gestire posizioni già aperte
```

Il sistema non deve vendere automaticamente.  
Deve solo produrre indicazioni informative.

---

## 5. Scelta architetturale chiave

Il sistema deve registrare **transazioni**, non posizioni statiche.

Le posizioni correnti devono essere calcolate automaticamente a partire dallo storico transazioni.

### Motivazione

Registrare transazioni è più robusto perché consente di gestire:

- acquisti multipli;
- vendite parziali;
- riacquisti;
- storico completo;
- commissioni;
- realized P/L;
- unrealized P/L;
- posizione residua;
- prezzo medio di carico.

Non bisogna creare una tabella modificabile manualmente delle posizioni correnti come fonte primaria.

La fonte primaria deve essere:

```text
transactions
```

La posizione è un dato derivato.

---

## 6. Metodo contabile iniziale

Per semplicità progettuale, il metodo iniziale deve essere:

```text
average cost
```

Quindi il prezzo medio di carico viene calcolato come costo medio ponderato.

FIFO, LIFO, tasse, dividendi, split e gestione fiscale non fanno parte della prima implementazione.

Potranno essere valutati in futuro.

---

# STEP 1 — Specifica strategia SELL

## Obiettivo

Creare o aggiornare un documento di strategia che definisca la logica SELL + un file di configurazione `config/sell_rules.yaml` con tutti i valori soglia.

Suggerimento file:

```text
docs/strategy/specifica_sell_strategy.md
```

Oppure integrare in:

```text
docs/strategy/specifiche_strategia.md
```

solo se coerente con la struttura già esistente.

## Principio strategico

La strategia SELL deve servire a gestire posizioni aperte dopo un ingresso Buy-the-Dip.

La logica base è:

```text
prendere profitto gradualmente quando il rimbalzo matura,
senza vendere automaticamente tutto a una soglia fissa.
```

## Stati SELL proposti

La strategia deve usare label informative, non ordini automatici.

Stati consigliati:

```text
MANTIENI
PRENDI PROFITTO PARZIALE
RIDUCI ESPOSIZIONE
ATTENZIONE
NESSUNA POSIZIONE
```

## Regole base consigliate

### Regola TP1 — Primo take profit

```text
Se unrealized_gain_pct >= +15%:
    suggerire PRENDI PROFITTO PARZIALE
```

Interpretazione:

- non vendere necessariamente tutto;
- valutare realizzo di circa 25–33% della posizione;
- mettere in sicurezza parte del guadagno.

---

### Regola TP2 — Secondo take profit

```text
Se unrealized_gain_pct >= +25%:
    suggerire PRENDI PROFITTO PARZIALE rafforzato
```

Interpretazione:

- valutare ulteriore realizzo di circa 25–33%;
- il rimbalzo Buy-the-Dip ha già prodotto un recupero significativo.

---

### Regola TP3 — Riduzione più aggressiva

```text
Se unrealized_gain_pct >= +30% o +40%
E almeno due segnali di surriscaldamento sono presenti:
    suggerire RIDUCI ESPOSIZIONE
```

Segnali di surriscaldamento:

- FGI >= 60;
- RSI >= 70;
- MFI >= 80;
- prezzo molto sopra SMA50;
- OBV non conferma il rialzo;
- upside residuo da target analyst basso o negativo, se disponibile.

---

### Regola HOLD — Lasciare correre

```text
Se la posizione è in gain
ma trend e volumi restano sani:
    suggerire MANTIENI
```

Condizioni favorevoli:

- prezzo sopra SMA50;
- prezzo sopra SMA200;
- RSI non estremo;
- MFI non estremo;
- OBV stabile o crescente;
- FGI non in extreme greed.

---

### Regola ATTENZIONE — Deterioramento

```text
Se posizione in perdita o in gain ridotto
E indicatori tecnici peggiorano:
    suggerire ATTENZIONE
```

Esempi:

- prezzo sotto SMA50;
- prezzo sotto SMA200;
- OBV in deterioramento;
- MFI debole;
- RSI debole;
- drawdown che peggiora dopo l’ingresso.

Questa regola non deve generare automaticamente un’uscita.

---

## Relazione con la strategia BUY

La strategia SELL non deve modificare il segnale BUY.

Esempio:

```text
ticker senza posizione aperta → usare logica BUY
ticker con posizione aperta → usare anche logica SELL
```

La strategia BUY risponde a:

```text
devo valutare un nuovo ingresso?
```

La strategia SELL risponde a:

```text
come devo gestire una posizione già aperta?
```

## Output atteso dello step

Alla fine dello step 1 devono esistere:

- specifica SELL scritta (`docs/strategy/specifica_sell_strategy.md`);
- file di configurazione soglie (`config/sell_rules.yaml`);
- regole chiare;
- stati SELL definiti;
- nessun codice applicativo obbligatorio modificato, salvo eventuali link documentali;
- nessuna modifica al comportamento runtime.

## Test richiesti

Non obbligatori se lo step è solo documentale.

Se vengono toccati file runtime o README, eseguire i test esistenti.

---

# STEP 2 — Database SQLite per transazioni

## Obiettivo

Aggiungere un database SQLite dedicato alle transazioni dell’utente.

Suggerimento file database:

```text
output/portfolio.db
```

Questo database deve essere separato da:

```text
output/scraper_audit.db
```

Motivo:

- `scraper_audit.db` riguarda audit tecnico degli scraper;
- `portfolio.db` riguarda dati utente e storico posizioni.

## Tabella principale

Creare tabella:

```text
transactions
```

Schema minimo:

```sql
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('BUY', 'SELL')),
    quantity REAL NOT NULL CHECK(quantity > 0),
    price_usd REAL NOT NULL CHECK(price_usd >= 0),
    commission_usd REAL NOT NULL DEFAULT 0 CHECK(commission_usd >= 0),
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

## Campi

### `trade_date`

Data dell’operazione.

Formato consigliato:

```text
YYYY-MM-DD
```

### `ticker`

Ticker normalizzato uppercase.

Esempi:

```text
NVDA
LMT
CEG
BE
```

### `action`

Valori ammessi:

```text
BUY
SELL
```

### `quantity`

Numero di azioni acquistate o vendute.

Deve essere maggiore di zero.

Supportare quantità decimali se possibile.

### `price_usd`

Prezzo unitario in USD.

### `commission_usd`

Commissione totale della transazione in USD.

Regola:

- per BUY aumenta il costo;
- per SELL riduce il ricavato netto.

### `note`

Campo libero opzionale.

### `created_at` / `updated_at`

Timestamp ISO.

## Funzioni richieste

Creare un modulo dedicato, ad esempio:

```text
src/portfolio_db.py
```

Responsabilità:

- inizializzare il DB;
- creare la tabella se non esiste;
- aggiungere transazione;
- modificare transazione;
- eliminare transazione;
- leggere tutte le transazioni;
- leggere transazioni per ticker;
- validare input.

## Regole di validazione

- ticker obbligatorio;
- ticker uppercase;
- action solo `BUY` o `SELL`;
- quantity > 0;
- price_usd >= 0;
- commission_usd >= 0;
- trade_date obbligatoria;
- note opzionale;
- nessun import da scraper;
- nessuna chiamata di rete.

## Non-obiettivi dello step

Non implementare ancora:

- pagina HTML;
- API web;
- strategia SELL;
- calcolo indicatori SELL;
- modifica del report principale.

## Test richiesti

Creare test dedicati, ad esempio:

```text
src/tests/test_portfolio_db.py
```

Test minimi:

- creazione DB;
- creazione tabella;
- insert BUY;
- insert SELL;
- update transazione;
- delete transazione;
- validazione action errata;
- validazione quantity <= 0;
- validazione price negativo;
- validazione commissione negativa;
- ticker normalizzato uppercase.

## Criteri di completamento

Lo step è concluso solo se:

- DB inizializzabile;
- CRUD transazioni funzionante via funzioni Python;
- test verdi;
- nessun impatto sulla pipeline scraping;
- nessun impatto sul report esistente.

---

# STEP 3 — Portfolio engine

## Obiettivo

Creare un modulo che calcoli le posizioni correnti a partire dalle transazioni.

Suggerimento file:

```text
src/portfolio.py
```

## Input

Il modulo deve ricevere:

```text
lista transazioni
```

Eventualmente, in futuro:

```text
prezzi correnti da output/output.json
indicatori da output/output.json
```

Ma in questo step iniziale il focus è calcolare le posizioni.

## Output posizione

Per ogni ticker con posizione aperta:

```text
ticker
quantity_current
average_entry_price_usd
total_cost_usd
realized_pnl_usd
realized_pnl_pct
market_price_usd opzionale
market_value_usd opzionale
unrealized_pnl_usd opzionale
unrealized_pnl_pct opzionale
total_pnl_usd opzionale
total_pnl_pct opzionale
```

## Regole average cost

### BUY

Quando arriva una transazione BUY:

```text
buy_cost = quantity * price_usd + commission_usd
new_total_cost = previous_total_cost + buy_cost
new_quantity = previous_quantity + quantity
average_entry_price = new_total_cost / new_quantity
```

### SELL

Quando arriva una transazione SELL:

```text
sell_proceeds = quantity * price_usd - commission_usd
cost_basis_sold = average_entry_price * quantity
realized_pnl = sell_proceeds - cost_basis_sold
remaining_quantity = previous_quantity - quantity
remaining_cost = average_entry_price * remaining_quantity
```

La vendita non deve cambiare il prezzo medio della quantità residua.

## Vincoli

- una SELL non può vendere più della quantità posseduta;
- se una posizione arriva a zero, può essere esclusa dalle posizioni aperte;
- lo storico deve restare disponibile nelle transazioni;
- usare ordinamento per `trade_date`, poi `id`;
- non gestire per ora tasse, dividendi, split o FIFO.

## Accumulatore realized P/L

Il motore deve calcolare le posizioni in un singolo passaggio cronologico
e **mantenere un accumulatore di realized P/L per ticker**:

```text
realized_pnl_accumulator_by_ticker: {ticker: total_realized_pnl_usd}
```

Questo accumulatore:

- viene incrementato a ogni SELL con il realized_pnl di quella singola vendita;
- **non viene resettato** a ogni ricalcolo — il dato è derivato dall'intero storico;
- viene restituito come parte dell'output del motore;
- è il valore che la pagina portfolio deve mostrare come "P/L realizzato".

## Integrazione con prezzi correnti

Se disponibile `last_close` da `output/output.json`, il modulo può calcolare:

```text
market_value_usd = quantity_current * last_close
unrealized_pnl_usd = market_value_usd - total_cost_usd
unrealized_pnl_pct = unrealized_pnl_usd / total_cost_usd * 100
```

Se il prezzo corrente è mancante:

```text
market_value_usd = null
unrealized_pnl = null
status = price_missing
```

Fail-safe:

```text
prezzo mancante non rompe il portfolio
```

## Test richiesti

Creare test dedicati:

```text
src/tests/test_portfolio.py
```

Test minimi:

- singolo BUY;
- due BUY stesso ticker;
- BUY + SELL parziale;
- BUY + SELL totale;
- riacquisto dopo vendita totale;
- SELL maggiore della posizione → errore;
- commissioni su BUY;
- commissioni su SELL;
- calcolo unrealized P/L con prezzo corrente;
- comportamento con prezzo mancante;
- realized_pnl_accumulator_by_ticker accumula su vendite multiple;
- vendite su ticker diversi sono indipendenti.

## Criteri di completamento

Lo step è concluso solo se:

- posizioni correnti calcolate correttamente;
- realized P/L calcolato;
- unrealized P/L calcolato se prezzo disponibile;
- test verdi;
- nessuna modifica obbligatoria alla UI.

---

# STEP 4 — API per transazioni e posizioni

## Obiettivo

Esporre endpoint locali per:

- aggiungere transazioni;
- modificare transazioni;
- eliminare transazioni;
- leggere transazioni;
- leggere posizioni calcolate.

Il progetto ha già un mini-server locale che serve pagine come:

```text
/report.html
/overrides.html
/tickers.html
```

La nuova funzionalità deve integrarsi nello stesso server, se coerente con l’architettura esistente.

## Endpoint minimi

### Transazioni

```text
GET /api/transactions
POST /api/transactions
PUT /api/transactions/{id}
DELETE /api/transactions/{id}
```

### Posizioni

```text
GET /api/positions
GET /api/positions/{ticker}
```

## Payload transazione

Esempio POST:

```json
{
  "trade_date": "2026-08-27",
  "ticker": "NVDA",
  "action": "BUY",
  "quantity": 10,
  "price_usd": 125.50,
  "commission_usd": 1.00,
  "note": "Ingresso iniziale"
}
```

## Risposta transazione

Esempio:

```json
{
  "ok": true,
  "transaction": {
    "id": 1,
    "trade_date": "2026-08-27",
    "ticker": "NVDA",
    "action": "BUY",
    "quantity": 10,
    "price_usd": 125.50,
    "commission_usd": 1.00,
    "note": "Ingresso iniziale",
    "created_at": "...",
    "updated_at": "..."
  }
}
```

## Errori

Gli errori devono essere chiari e JSON.

Esempio:

```json
{
  "ok": false,
  "error": "quantity must be greater than 0"
}
```

## Sicurezza

Le API devono usare la stessa protezione già prevista dal mini-server locale.

Se il server usa Basic Auth, anche queste API devono richiederla.

## Non-obiettivi dello step

Non implementare ancora:

- UI completa;
- strategia SELL;
- grafici;
- import broker;
- export fiscale.

## Test richiesti

Se il progetto ha test sul server/API, aggiungere test per:

- GET transactions;
- POST transaction valida;
- POST transaction non valida;
- PUT transaction;
- DELETE transaction;
- GET positions;
- autenticazione, se già testata altrove.

Se i test server sono troppo onerosi, almeno testare le funzioni handler pure o il modulo sottostante.

## Criteri di completamento

Lo step è concluso solo se:

- API CRUD funzionano;
- validazioni attive;
- posizioni leggibili via API;
- nessun impatto negativo su `/report.html`, `/overrides.html`, `/tickers.html`;
- test verdi.

---

# STEP 5 — Pagina HTML portfolio

## Obiettivo

Creare una nuova pagina HTML per gestione transazioni e visione posizioni.

Percorso consigliato:

```text
/positions.html
```

Oppure:

```text
/portfolio.html
```

La pagina deve essere semplice e funzionale.

## Sezioni pagina

### 1. Riepilogo portfolio

Mostrare:

```text
valore corrente totale
capitale investito
P/L non realizzato
P/L realizzato
P/L totale
numero posizioni aperte
```

Se alcuni prezzi correnti sono mancanti, mostrare warning.

### 2. Posizioni aperte

Tabella con colonne:

```text
Ticker
Quantità
Prezzo medio USD
Ultimo prezzo USD
Valore corrente USD
Costo totale USD
Gain/Loss USD
Gain/Loss %
Stato dati prezzo
```

### 3. Transazioni

Tabella con colonne:

```text
Data
Ticker
BUY/SELL
Quantità
Prezzo USD
Commissione USD
Note
Azioni
```

Azioni:

```text
modifica
elimina
```

### 4. Form transazione

Campi:

```text
trade_date
ticker
action
quantity
price_usd
commission_usd
note
```

Funzioni:

- aggiungi transazione;
- modifica transazione esistente;
- annulla modifica;
- elimina con conferma.

## Vincoli UI

- mantenere stile coerente con report esistente;
- niente framework pesanti;
- JavaScript inline semplice se il progetto usa già pagine statiche;
- usare API locali;
- mostrare errori chiari;
- non duplicare logica di calcolo nel frontend;
- il frontend deve chiamare API, non ricalcolare il portfolio.

## Non-obiettivi dello step

Non implementare ancora:

- strategia SELL;
- suggerimenti di uscita;
- grafici avanzati;
- import CSV broker;
- autenticazione nuova se già esistente.

## Test richiesti

Se il progetto ha test HTML/server:

- pagina servita;
- endpoint raggiungibili;
- form invia payload corretto;
- tabella riceve dati mock.

In alternativa:

- testare generazione HTML;
- testare funzioni helper;
- verifica manuale documentata.

## Criteri di completamento

Lo step è concluso solo se:

- pagina accessibile;
- transazioni CRUD funzionano da UI;
- posizioni aperte visibili;
- errori validazione leggibili;
- nessun impatto su report principale;
- test o verifica manuale completati.

---

# STEP 6 — SELL evaluation per posizioni aperte

## Obiettivo

Aggiungere valutazione SELL alle posizioni attualmente aperte.

Questa valutazione deve usare:

1. dati posizione;
2. storico transazioni;
3. prezzi correnti;
4. indicatori tecnici già scrapati;
5. FGI e altri indicatori macro già disponibili;
6. eventuale fair value, solo come supporto secondario/display-context.

## Modulo consigliato

Creare modulo dedicato:

```text
src/sell_strategy.py
```

Responsabilità:

- ricevere posizione;
- ricevere indicatori ticker;
- ricevere dati macro;
- calcolare suggerimento SELL;
- restituire motivazioni leggibili.

## Input minimo

Per ogni posizione:

```text
ticker
quantity_current
average_entry_price_usd
total_cost_usd
market_price_usd
unrealized_pnl_usd
unrealized_pnl_pct
realized_pnl_usd
```

Indicatori ticker:

```text
RSI
MFI
OBV
SMA50
SMA200
drawdown_52w
last_close
```

Indicatori macro:

```text
FGI
VIX opzionale
PCR opzionale
breadth opzionale
```

Valuation opzionale:

```text
upside_pct
target_median
forward_pe
peg
valuation_status
```

## Output SELL

Per ogni posizione aperta:

```json
{
  "ticker": "NVDA",
  "sell_signal": "PRENDI PROFITTO PARZIALE",
  "confidence": "medium",
  "reasons": [
    "Gain non realizzato superiore al 15%",
    "RSI vicino a zona surriscaldata",
    "FGI non più in fear"
  ],
  "suggested_action_note": "Valutare realizzo parziale, non uscita totale automatica."
}
```

## Regole concrete iniziali

### Nessuna posizione

```text
quantity_current <= 0 → NESSUNA POSIZIONE
```

### Mantieni

```text
unrealized_gain_pct < 15
E nessun deterioramento tecnico forte
→ MANTIENI
```

### Take profit parziale base

```text
unrealized_gain_pct >= 15
→ PRENDI PROFITTO PARZIALE
```

### Take profit rafforzato

```text
unrealized_gain_pct >= 25
→ PRENDI PROFITTO PARZIALE
```

Con motivazione rafforzata.

### Riduci esposizione

```text
unrealized_gain_pct >= 30
E almeno 2 condizioni vere:
    FGI >= 60
    RSI >= 70
    MFI >= 80
    prezzo > SMA50 del 10% o più
    OBV debole/non confermante
→ RIDUCI ESPOSIZIONE
```

### Attenzione

```text
unrealized_gain_pct <= 0
E almeno 2 condizioni tecniche negative:
    prezzo sotto SMA50
    prezzo sotto SMA200
    RSI < 45
    MFI < 40
    OBV in deterioramento
→ ATTENZIONE
```

## Fair value nella SELL strategy

Il fair value deve restare secondario.

Non deve generare da solo un segnale SELL.

Può contribuire come warning se:

```text
posizione già in forte gain
E upside_pct residuo basso o negativo
E RSI/MFI/FGI indicano surriscaldamento
```

Esempio:

```text
gain >= 25%
upside_pct <= 5%
RSI >= 70
→ rafforza PRENDI PROFITTO PARZIALE
```

Se fair value mancante/stale:

```text
nessun impatto
```

## Interazione con BUY strategy

La SELL strategy non deve modificare:

```text
VALUTA INGRESSO / OSSERVA / ATTENDI
```

relativi ai ticker senza posizione.

La pagina portfolio può mostrare il SELL signal solo per ticker detenuti.

Il report principale può eventualmente mostrare una nota:

```text
ticker già in portafoglio: vedere pagina portfolio
```

ma non è obbligatorio nel primo rilascio.

## Test richiesti

Creare:

```text
src/tests/test_sell_strategy.py
```

Test minimi:

- posizione non aperta → NESSUNA POSIZIONE;
- gain +10% → MANTIENI;
- gain +15% → PRENDI PROFITTO PARZIALE;
- gain +25% → PRENDI PROFITTO PARZIALE rafforzato;
- gain +35% + RSI alto + FGI alto → RIDUCI ESPOSIZIONE;
- gain negativo + indicatori tecnici deboli → ATTENZIONE;
- fair value mancante non rompe;
- fair value non genera SELL da solo;
- indicatori mancanti producono output prudente;
- nessuna regola SELL modifica segnali BUY.

## Criteri di completamento

Lo step è concluso solo se:

- SELL evaluation calcolata per posizioni aperte;
- output motivato e leggibile;
- UI portfolio mostra il segnale SELL;
- test verdi;
- BUY strategy invariata;
- report principale non rotto.

---

# STEP 7 — Integrazione opzionale nel report principale

## Obiettivo

Valutare se mostrare nel report principale una sintesi leggera delle posizioni detenute.

Questa fase è opzionale.

## Possibile integrazione

Nel report HTML principale:

- badge “in portafoglio” accanto al ticker;
- quantità posseduta;
- gain/loss %;
- link a `/positions.html`;
- eventuale SELL signal sintetico.

## Vincoli

Non appesantire il report principale.

La pagina portfolio deve restare il luogo primario per:

- transazioni;
- posizioni;
- SELL evaluation;
- P/L.

## Criteri di completamento

Solo se implementato:

- report resta leggibile;
- nessuna duplicazione eccessiva;
- link alla pagina portfolio funzionante;
- test aggiornati.

---

# Non-obiettivi globali della prima versione

La prima versione non deve includere:

- gestione fiscale;
- FIFO fiscale;
- LIFO;
- dividendi;
- stock split;
- opzioni;
- short selling;
- margin;
- cash balance completo;
- multi-currency;
- import automatico da broker;
- esportazione fiscale;
- performance annualizzata complessa;
- grafici avanzati;
- backtest sofisticato.

Questi potranno essere considerati in futuro.

---

# Regole di fail-safe

## Dati prezzo mancanti

Se manca il prezzo corrente:

```text
posizione calcolata
ma P/L corrente non calcolabile
```

Mostrare warning.

## Indicatori tecnici mancanti

Se mancano indicatori tecnici:

```text
SELL evaluation prudente
confidence = low
```

Non generare suggerimenti aggressivi.

## FGI mancante

Per la BUY strategy resta fail-closed.

Per la SELL strategy:

```text
FGI mancante non deve impedire calcolo P/L
ma riduce confidence del suggerimento SELL
```

## Fair value mancante/stale

```text
nessun impatto operativo
nessun blocco
nessun bonus
mostrare solo come dato non disponibile
```

---

# Modello dati suggerito

## Database

File:

```text
output/portfolio.db
```

Tabella:

```text
transactions
```

Campi:

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
trade_date TEXT NOT NULL
ticker TEXT NOT NULL
action TEXT NOT NULL
quantity REAL NOT NULL
price_usd REAL NOT NULL
commission_usd REAL NOT NULL DEFAULT 0
note TEXT
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
```

## Oggetto posizione derivata

```json
{
  "ticker": "NVDA",
  "quantity_current": 10,
  "average_entry_price_usd": 125.50,
  "total_cost_usd": 1256.00,
  "market_price_usd": 145.00,
  "market_value_usd": 1450.00,
  "unrealized_pnl_usd": 194.00,
  "unrealized_pnl_pct": 15.45,
  "realized_pnl_usd": 0.00,
  "total_pnl_usd": 194.00,
  "total_pnl_pct": 15.45
}
```

## Oggetto SELL evaluation

```json
{
  "ticker": "NVDA",
  "sell_signal": "PRENDI PROFITTO PARZIALE",
  "confidence": "medium",
  "reasons": [
    "Gain non realizzato superiore al 15%",
    "Il titolo ha raggiunto la prima soglia di take profit"
  ],
  "suggested_action_note": "Valutare realizzo parziale di circa 25-33% della posizione."
}
```

---

# Relazione con indicator_registry.yaml

La funzionalità portfolio/SELL non deve entrare automaticamente nel registry degli indicatori BUY.

Se in futuro si vuole formalizzare la SELL strategy nel registry, creare una sezione separata o un registry dedicato.

Esempio futuro:

```text
sell_indicator_registry.yaml
```

Per ora evitare di contaminare:

```text
indicator_registry.yaml
```

se questo è pensato per la strategia BUY.

---

# Requisiti di semplicità

Per tutta la prima implementazione:

1. preferire funzioni pure dove possibile;
2. mantenere moduli piccoli;
3. evitare refactor globale;
4. non modificare scraper esistenti salvo necessità;
5. non modificare la logica BUY;
6. non cambiare il gate FGI già implementato;
7. testare ogni step;
8. non introdurre dipendenze pesanti;
9. usare SQLite standard;
10. mantenere compatibilità con flusso `run.py`.

---

# Sequenza finale raccomandata

La roadmap ufficiale della funzionalità è:

```text
STEP 1 — Specifica SELL strategy
STEP 2 — Database SQLite transazioni
STEP 3 — Portfolio engine
STEP 4 — API CRUD transazioni/posizioni
STEP 5 — Pagina HTML portfolio
STEP 6 — SELL evaluation sulle posizioni
STEP 7 — Integrazione opzionale nel report principale
```

Ogni step deve essere completato prima di iniziare il successivo.

---

# Definition of Done globale

La funzionalità è considerata completa quando:

1. l’utente può registrare BUY e SELL;
2. lo storico transazioni è persistente in SQLite;
3. le posizioni aperte sono calcolate automaticamente;
4. vendite parziali e riacquisti sono gestiti;
5. commissioni in USD sono incluse;
6. la pagina portfolio mostra posizioni e transazioni;
7. la pagina consente aggiunta, modifica ed eliminazione transazioni;
8. ogni posizione aperta riceve una valutazione SELL;
9. la valutazione SELL è motivata;
10. la strategia BUY esistente resta invariata;
11. i test sono verdi;
12. il sistema mantiene comportamento fail-safe su dati mancanti.

---

# Nota finale

Questa funzionalità deve essere trattata come estensione del progetto, non come sostituzione della pipeline esistente.

La pipeline attuale risponde alla domanda:

```text
quali ticker sono interessanti per valutare ingressi Buy-the-Dip?
```

La nuova funzionalità portfolio risponde alla domanda:

```text
date le posizioni che possiedo, come dovrei monitorarle e quando valutare prese di profitto o riduzioni?
```

Le due logiche devono restare separate, ma possono condividere gli stessi dati scrapati.