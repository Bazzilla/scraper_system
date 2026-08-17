# Design: Validità temporale dinamica nel report HTML

**Data**: 2026-08-17
**Stato**: approvato (brainstorming)
**Area**: `src/report_html.py` + test

## Problema

Il report HTML mostra badge `fresh`/`stale` calcolati **server-side al momento della generazione** (dal consolidator). Se il file viene aperto giorni dopo, i badge restano congelati al momento della generazione: un dato daily appare "fresh" anche se è ormai vecchio di 3 giorni. L'utente vuole che il report indichi la **validità temporale reale** del dato (obsolescenza) rispetto alla data odierna.

Ogni sorgente ha già nel JSON i campi necessari: `fetched_at` (timestamp ISO) e `stale_after_hours` (ore di validità, diversi per indice: FGI 24h, AAII 168h, VIX 24h, ecc.).

## Approccio scelto

**JS client-side puro** (Approccio A): il report resta una pagina statica self-contained; uno script JavaScript al caricamento ricalcola l'età di ogni dato rispetto a `Date.now()` e aggiorna badge + testo età. Il badge server-side resta come fallback se JS è disabilitato.

## Meccanismo

1. **Python** (`report_html.py`) aggiunge attributi `data-*` agli elementi HTML che hanno un timestamp:
   - `data-fetched-at` → timestamp ISO del dato
   - `data-stale-hours` → ore di validità (`stale_after_hours`)
2. **JavaScript** (esteso `_SCRIPT`) al caricamento:
   - Trova tutti gli elementi con `data-fetched-at`
   - Calcola età = `Date.now() - fetched_at`
   - Se età > `stale_after_hours` → badge **stale** (rosso) + testo "scaduto da X"
   - Altrimenti → badge **fresh** (verde) + testo "aggiornato X fa · scade tra Y"
   - Formato compatto italiano: `45min fa`, `2h fa`, `3g fa`

## Componenti

| Componente | Cosa fa |
|---|---|
| `_age_attrs(fetched_at, stale_after_hours)` | Helper Python che genera `data-fetched-at="..." data-stale-hours="..."` (stringa vuota se manca il timestamp) |
| `_SCRIPT` esteso | JS che ricalcola badge + testo età al caricamento (aggiunto al blocco script esistente del theme toggle) |
| CSS aggiuntivo | Classe `.age` per il testo età (colore muted, dimensione ridotta) |

## Punti di applicazione

1. **Card indicatori di mercato** (`render_market_cards`): ogni card riceve `data-*` dalla sua sorgente principale:
   - FGI → `fgi`, VIX → `vix`, PCR → `pcr`, AAII → `aaii`, NAAIM → `naaim`, breadth → `pct_sma`, insider → `insider`
   - Nota: la VIX Term Structure non ha una card propria — è solo una nota dentro la card VIX, quindi usa `vix` come timestamp di riferimento
   - Il JS aggiorna il badge e aggiunge il testo età nell'ultimo `.meta` della card (le card breadth e insider ne hanno due: riga dati + riga "Aggiornato:")
2. **Tabelle ticker** (`render_ticker_table`): ogni riga `<tr>` riceve `data-*` dal `fetched_at` del ticker. Il JS aggiorna la cella "Aggiornato" con il testo età.

**Escluso**: la matrice indicatori (`render_indicator_matrix`) resta invariata — mostra già availability/source, non ha un timestamp diretto per riga.

## Fallback

- JS disabilitato → badge server-side esistenti restano (l'header overall; le card/righe non avevano badge per-card server-side prima di questa feature — il JS li crea dinamicamente)
- Card di errore (`_error_card`) → nessun `data-*` (non c'è timestamp)
- Dati senza `fetched_at` → nessun `data-*`, il JS li ignora
- `fetched_at` nel futuro (clock skew) → età clampata a 0 (mai "aggiornato -Xmin fa")

## Test

- Test unitari Python:
  - `_age_attrs` genera gli attributi corretti con timestamp valido
  - `_age_attrs` restituisce stringa vuota con `fetched_at=None`
  - L'HTML generato da `render_market_cards` contiene `data-fetched-at`/`data-stale-hours` nelle card
  - L'HTML generato da `render_ticker_table` contiene `data-fetched-at`/`data-stale-hours` nelle righe
- Verifica manuale: aprire `report.html` e controllare badge + testo età

## Criteri di uscita

- [ ] `report_html.py` genera attributi `data-*` nelle card indicatori e nelle righe ticker
- [ ] Lo script JS ricalcola badge e testo età al caricamento
- [ ] Test unitari aggiornati e verdi (suite completa 224+ test)
- [ ] Verifica manuale: report aperto mostra "aggiornato X fa · scade tra Y" / "scaduto da X"