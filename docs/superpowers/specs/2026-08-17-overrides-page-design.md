# Design: Pagina di immissione manual overrides + mini-server

**Data**: 2026-08-17
**Stato**: approvato (brainstorming)
**Area**: `src/overrides_server.py` (nuovo), `src/overrides_page.py` (nuovo), `src/manual_overrides.py`, `src/report_html.py`, test

## Problema

Immettere valori manuali oggi richiede editare `manual_overrides.yaml` a mano (scommentare voci, aggiornare `fetched_at`, riavviare `run.py --override-only`). L'utente vuole una pagina HTML che permetta di immettere/aggiornare i valori con un pulsante WRITE, un flag `enabled` per-riga, e che **rigeneri automaticamente il report HTML** dopo ogni salvataggio.

## Approccio scelto

**Mini-server Python locale** (stdlib `http.server`, zero dipendenze) che serve:
- `GET /` → la pagina di immissione (`overrides.html`)
- `GET /api/data` → legge `manual_overrides.yaml` e restituisce JSON (valori attuali + enabled)
- `POST /api/save` → valida e scrive `manual_overrides.yaml` (valori + `fetched_at=now`), poi **rigenera output.json + report.html** applicando gli override all'output esistente (logica `run.py --override-only`, nessuno scraping)
- `GET /report.html` → serve `output/report.html` esistente (per il link di navigazione)

Bind su `127.0.0.1`, single-user, niente autenticazione (uso domestico).

## Componenti

| Componente | Cosa fa |
|---|---|
| `src/overrides_server.py` (nuovo) | Mini-server HTTP stdlib: router GET/POST, valida con `validate_entry`, scrive YAML con `yaml.safe_dump`, chiama `rebuild_report()` dopo il save. CLI: `python overrides_server.py [--port 8000]` |
| `src/overrides_page.py` (nuovo) | Funzioni che generano la pagina HTML (`render_overrides_page(overrides: dict) -> str`), riusando `_CSS`/`_SCRIPT` di `report_html.py` (stessi stili + theme-toggle). Include il JS fetch che carica `/api/data` e invia POST `/api/save` |
| `src/manual_overrides.py` | Esteso: (1) flag `enabled` per-riga (default `true` se assente, retrocompatibile); (2) `save_override(path, key, values, enabled)` che scrive il YAML aggiornato con `fetched_at` fresco (UTC now) |
| `src/report_html.py` | Header: link "Immissione manuale" → `/overrides.html` |

## Flag `enabled` per-riga

- Nel YAML: `enabled: true/false` (default **true** se assente → retrocompatibile con file esistenti)
- `enabled: false` → `apply_overrides` **ignora** l'override anche se presente/valido (come se non esistesse)
- Separato da `strategy.force_manual_overrides` (config.yaml) che resta per forzare il manuale su scraper fresh

Modifiche a `manual_overrides.py`:
- `validate_entry`: accetta e conserva `enabled` (bool, default true)
- `build_manual_result`: invariato (usa i campi valore)
- `apply_overrides`: salta gli override con `enabled: false`
- `load_validated_overrides`: passa `enabled` nel dict validato

## Pagina `overrides.html`

- Header: titolo, link "← Vai al report" → `/report.html`, theme-toggle (CSS/JS condivisi con `report_html.py`)
- Una **card per indicatore attivo** in `manual_overrides.yaml` (oggi 5: aaii, fgi, naaim, vix_term_structure, pct_sma):
  - Nome + badge (`manual_supported` per naaim/vix_ts/pct_sma; `fallback` per aaii/fgi che hanno anche lo scraper)
  - Checkbox "abilitato" (flag `enabled`)
  - Campi specifici precompilati dai valori attuali:
    - aaii → bullish, neutral, bearish
    - fgi → score, zone (testo)
    - naaim → exposure
    - vix_term_structure → m1, m2
    - pct_sma → pct_sma50, pct_sma200
  - `stale_after_hours` (numero) e `note` (testo) editabili
  - Pulsante **WRITE** → POST `/api/save` → conferma visiva
- Il server valida lato server (`validate_entry`) e rifiuta valori malformati con messaggio d'errore

## Rigenerazione report dopo il save

Il server, dopo aver scritto il YAML, replica la logica di `run.py mode_override_only` (nessuno scraping):
1. Carica config + output.json esistente
2. Ricostruisce i results dal persisted output (drop meta keys)
3. `load_validated_overrides` + `apply_overrides` (priorità scraping > manual > missing)
4. `consolidate(results)` + `_build_strategy_indicators(config, base_dir, results)`
5. Scrive `output/output.json` e `render(config_path)` → `output/report.html`

Implementata come funzione `rebuild_report(config_path: str) -> None` nel server (replica della logica, senza print CLI di run.py).

## Link reciproci

- `report.html` header → link "Immissione manuale" → `/overrides.html`
- `overrides.html` header → link "Vai al report" → `/report.html`
- Il server serve entrambe alla stessa origin

## Sicurezza

- Validazione lato server con `validate_entry` (whitelist dei 5 indicatori supportati)
- Scrittura solo con `yaml.safe_dump` di un dict costruito (no injection YAML)
- Bind `127.0.0.1` (solo localhost), single-user
- Nessun dato sensibile

## Test

- `manual_overrides`:
  - `validate_entry` con `enabled: false` → conservato; assente → default true
  - `apply_overrides` con `enabled: false` → override ignorato (scraping/missing resta)
  - `save_override` → scrive YAML con `fetched_at` aggiornato, valori + enabled conservati, altri indicatori intatti
- `overrides_server` (test con file temp):
  - `GET /api/data` → JSON con valori + enabled correnti
  - `POST /api/save` valido → YAML aggiornato + report rigenerato (mock di `rebuild_report` per isolare)
  - `POST /api/save` invalido → 400 + YAML invariato
  - `POST /api/save` con key non supportata → 400
- `report_html`:
  - Header contiene link "Immissione manuale" → `/overrides.html`

## Non modificati

- `config.yaml` (il flag enabled vive nel YAML overrides, non in config)
- `indicator_registry.yaml` (gli indicatori restano `manual_supported`)
- Scraping/scoring esistente (nessun cambio di semantica, solo il flag enabled)

## Criteri di uscita

- [ ] `python src/overrides_server.py` serve la pagina + API
- [ ] WRITE aggiorna `manual_overrides.yaml` con `fetched_at` fresco
- [ ] Dopo il save, `output/report.html` viene rigenerato automaticamente
- [ ] `enabled: false` → override ignorato nel pipeline
- [ ] Link reciproci report ↔ overrides
- [ ] Stessi stili + theme-toggle
- [ ] Suite completa verde