# Design: Componenti FGI (7 sotto-indicatori) dal payload CNN

**Data**: 2026-08-17
**Stato**: approvato (brainstorming)
**Area**: `src/scrapers/fgi_scraper.py` + `src/report_html.py` + test

## Problema

L'API CNN usata dallo scraper FGI (`production.dataviz.cnn.io/index/fearandgreed/graphdata`) espone già i **7 sotto-indicatori** del Fear & Greed Index, ognuno con `score` (0-100), `rating` (label sintetica: extreme fear / fear / neutral / greed / extreme greed), `timestamp` e serie storica `data`. Lo scraper attuale estrae solo `score` + `rating` dal payload, ignorando i 7 componenti.

L'utente vuole questi valori come **informazione aggiuntiva** nel report HTML e nell'output strutturato — NON devono entrare nel calcolo del segnale/scoring.

## Comportamento (opzione B)

- **Fonte CNN disponibile** → i 7 componenti vengono estratti e mostrati (nested in `fgi.fgi_components`)
- **Fonte CNN non disponibile** (fallback su feargreedmeter/feargreedindex) → il composito FGI resta come oggi, i componenti risultano **mancanti** (nessun fallback debole inventato)

## Mapping chiavi API → chiavi progetto

| Chiave API CNN | Chiave progetto (snake_case) |
|---|---|
| `market_momentum_sp500` | `market_momentum` |
| `stock_price_strength` | `stock_price_strength` |
| `stock_price_breadth` | `stock_price_breadth` |
| `put_call_options` | `put_call_options` |
| `market_volatility_vix` | `market_volatility` |
| `junk_bond_demand` | `junk_bond_demand` |
| `safe_haven_demand` | `safe_haven_demand` |

Ogni componente nel nostro output: `{"score": float, "rating": str}`.

## Componenti

| Componente | Cosa fa |
|---|---|
| `parse_components(payload) -> dict` | Nuova funzione in `fgi_scraper.py` — mappa le 7 chiavi CNN in chiavi snake_case progetto, estraendo `score` (float) e `rating` (str) da ciascuna. Se una chiave manca o è malformata, la salta (fail-soft sul singolo componente) |
| `parse_cnn()` esteso | Oltre a `score`/`zone`, richiama `parse_components` e aggiunge `fgi_components` al risultato |
| `build_result(..., fgi_components=None)` | Accetta i componenti e li mette nested in `fgi_components` (default `None` → chiave assente) |
| `run()` | Passa i componenti a `build_result` solo quando la fonte vincente è `cnn` |
| `render_market_cards` (card FGI) | Mostra il punteggio sintetico come oggi + **mini-griglia compatta** sotto con i 7 componenti: nome + score + rating (colore semaforo da `semaphore_class`) |

## Struttura dati output

```json
"fgi": {
  "score": 64.97,
  "zone": "greed",
  "fetched_at": "...",
  "frequency": "daily",
  "stale_after_hours": 24,
  "status": "fresh",
  "source": "cnn",
  "fgi_components": {
    "market_momentum": {"score": 74.6, "rating": "greed"},
    "stock_price_strength": {"score": 28.6, "rating": "fear"},
    "...": "..."
  }
}
```

Se fonte ≠ cnn, `fgi_components` è **assente** (nessuna chiave vuota, nessun placeholder).

## Fallback e casi limite

- Fonte non-CNN → `fgi_components` assente, nessun crash
- Componente mancante/malformato nel payload CNN → componente saltato (gli altri restano)
- Nessun componente valido → `fgi_components` assente (come fonte non-CNN)
- Report: card FGI senza componenti → nessuna mini-griglia, card identica a oggi

## Non modificati

- `config.yaml`, `indicator_registry.yaml`, `manual_overrides.yaml` — nessuna voce nuova (i componenti sono informativi, non indicatori strategici)
- Scoring/segnale (`compute_signal`, gate FGI) — invariati

## Test

- `test_fgi_scraper.py`:
  - `parse_components` su payload completo → 7 componenti con score/rating
  - `parse_components` su payload con chiave mancante → componente saltato
  - `parse_cnn` su payload reale → include `fgi_components`
  - `build_result` con componenti → chiave nested presente
  - `build_result` senza componenti → chiave assente
- `test_report_html.py`:
  - Card FGI con componenti → mini-griglia renderizzata (nome + score + rating)
  - Card FGI senza componenti → nessuna mini-griglia, card invariata

## Criteri di uscita

- [ ] `parse_cnn` estrae score + 7 componenti dal payload reale CNN
- [ ] `output.json` → `fgi.fgi_components` con i 7 sub-indicatori quando fonte CNN
- [ ] Card FGI nel report mostra la mini-griglia con score+rating per componente
- [ ] Fonte non-CNN → `fgi_components` assente, nessun crash
- [ ] Suite completa verde (234 + nuovi test)