# Design: Modulo insider_scraper (Bonus Insider Transactions)

**Data**: 2026-08-12
**Stato**: Approvato
**Scope**: Nuovo modulo scraper per il bonus insider della strategia buy-the-dip (OpenInsider)

## Obiettivo

Creare `src/scrapers/insider_scraper.py` che legge la pagina OpenInsider
"Latest Officer Purchases $25k+" e calcola, per ogni ticker del config (29),
il **bonus insider** della strategia (specifiche_strategia.md H5):
- **+0.5** se ≥2 acquisti insider (dirigenti) in 4 settimane, open market,
  valore > $100K
- **+1.0** se CEO/CFO compra sul mercato aperto
- Cumulabile, **max +1.5**

## Fonte

- **URL**: `http://openinsider.com/latest-officer-purchases-25k`
- **Metodo**: GET via **HTTP** (HTTPS fallisce sul server OpenInsider — connessione rifiutata; HTTP risponde 200)
- **Dato**: tabella transazioni (`class="tinytable"`), colonne: Filing Date, Trade
  Date, Ticker, Company, Insider Name, **Role**, Trade Type, Price, Qty, Value
- **Lag**: 2 giorni (Form 4 SEC)
- La pagina **officer include già CEO/CFO** (verificato: 18 occorrenze CEO/CFO) —
  si scansiona UNA sola pagina, il ruolo è nella colonna `role`

## Logica bonus (per i 29 ticker del config)

Per ogni ticker presente sia nel config che nella pagina:
1. Filtra `trade_type == "P - Purchase"` e `trade_date >= today - days_back` (30)
2. **Officer bonus**: `+0.5` se `count(purchases) >= 2` E `sum(value) > 100000`
3. **CEO/CFO bonus**: `+1.0` se almeno un acquisto ha `role` in
   (CEO, CFO, Chief Executive, Chief Financial Officer)
4. `total_bonus = min(officer_bonus + ceo_cfo_bonus, 1.5)`

## Output (formato file.json)

```json
"insider": {
  "semiconductors": {
    "AMAT": { "purchases_30d": 2, "total_value_30d": 450000, "ceo_cfo": false,
              "officer_bonus": 0.5, "ceo_cfo_bonus": 0.0, "total_bonus": 0.5,
              "last_trade_date": "2026-08-10" }
  },
  "defense": { ... },
  "total": { "tickers_with_bonus": 3, "max_bonus": 1.0, "max_ticker": "AMAT" },
  "fetched_at": "...", "frequency": "daily", "stale_after_hours": 24, "status": "fresh"
}
```

- Per ticker: counts/valori degli acquisti recenti + bonus calcolati
- `total`: sintesi (ticker con bonus, max bonus, ticker con max bonus)
- `status` fresh se il fetch è riuscito (anche senza acquisti per i nostri ticker)

## Pattern del modulo

Segue il contratto `run(config) -> dict` (pattern fgi/pcr):
- `fetch_page(session, url, timeout) -> str` — DI rete
- `parse_rows(html: str) -> list[dict]` — **funzione pura** (estrazione righe)
- `filter_recent(rows, days_back) -> list[dict]` — funzione pura
- `compute_bonuses(rows, tickers, min_value) -> dict` — funzione pura
- `build_result(per_ticker, totals, fetched_at) -> dict` — funzione pura
- `run(config)` — fetch + orchestrazione

## Parsing delle righe

Ogni `<tr>` della tabella `tinytable` contiene le celle nell'ordine noto.
Estraggo con regex/BS4: ticker (link `/TICKER`), insider name, **role** (`<td>CEO</td>`),
trade type (`<td>P - Purchase</td>`), price, qty (`+3,850`), value (`+$202,554`),
trade date (`<div>2026-06-09</div>`). Valori numerici de-formattati (rimuovi `$`, `,`, `+`).

## Config.yaml

```yaml
insider:
  module: scrapers.insider_scraper
  output_key: insider
  schedule: daily
  config:
    url: "http://openinsider.com/latest-officer-purchases-25k"
    timeout: 20
    retries: 3
    backoff: 2.0
    headers:
      User-Agent: "Mozilla/5.0 ..."
    days_back: 30
    min_value: 100000
    stale_after_hours: 24
```

## Report HTML

- **Card "Insider"** nel gruppo mercato: ticker con bonus, max bonus, max ticker
- **Legenda**: spiegazione bonus strategia H5
  (Nota: il dettaglio per-ticker con bonus > 0 del design iniziale non è stato
  implementato — scoped-down a card + legenda nel piano. Future work opzionale.)
- **compute_signal NON cambia** — l'insider è bonus opportunità (H5), non scoring ticker

## File

```
src/scrapers/insider_scraper.py
src/tests/test_insider_scraper.py
config.yaml (sezione insider)
src/report_html.py (card insider + legenda)
src/tests/test_report_html.py (test card)
```

## Manutenibilità strategia

`insider` **non entra in compute_signal** — è un bonus della matrice Opportunità
(H5), applicato a livello di report/sintesi, non allo scoring per-ticker. Annotare
nel ledger: se in futuro la strategia volesse integrare il bonus nello scoring,
andrebbe aggiunto con logica dedicata.

## Fuori scope

- Analisi vendite insider (la strategia usa solo gli acquisti)
- Verifica Form 4 individuali SEC (OpenInsider già aggrega)
- Modifiche a compute_signal
- Scheduler
