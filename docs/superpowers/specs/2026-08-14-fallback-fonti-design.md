# Design: Fallback fonti (pattern generico)

**Data**: 2026-08-14
**Stato**: Approvato
**Scope**: Helper generico per fallback fonti + applicazione a FGI e AAII

## Obiettivo

Rendere i moduli scraper più resilienti alle fonti instabili. La Roadmap cita
esplicitamente "Aggiungere fallback per fonti instabili (es. FGI)". Creare un
pattern **generico riusabile** (`src/fetch_utils.py`) e applicarlo a **FGI**
(fonte secondaria alternative.me) e **AAII** (consolidamento del fallback
interno esistente dataChart5 → HTML bars).

## Architettura

### Nuovo modulo `src/fetch_utils.py`

```python
def fetch_first_success(
    session: requests.Session,
    sources: list[tuple[str, str]],
    timeout: int,
    retries: int,
    backoff: float,
) -> tuple[str, str]:
    """Prova più fonti (name, url) in sequenza.

    Returns:
        (body, source_name) della prima fonte che risponde.
    Raises:
        RuntimeError: se tutte le fonti falliscono.
    """

def try_parsers(
    body: str,
    parsers: list[tuple[str, Callable[[str], Any]]],
) -> tuple[Any, str]:
    """Prova più parser (name, func) sullo stesso body.

    Returns:
        (result, parser_name) del primo parser che riesce.
    Raises:
        ValueError: se tutti i parser falliscono.
    """
```

- `fetch_first_success`: per ogni `(name, url)` in `sources`, tenta il fetch con
  retry/backoff; al primo successo ritorna `(body, name)`; se tutti falliscono
  solleva RuntimeError con l'elenco dei nomi falliti.
- `try_parsers`: per ogni `(name, func)` in `parsers`, tenta `func(body)`; al
  primo successo ritorna `(result, name)`; se tutti falliscono solleva ValueError.
- Funzioni pure (tranne il fetch che usa la session iniettata — DI rete).

## Applicazione a FGI (`fgi_scraper.py`)

Fonti in ordine di priorità (tutte misurano il **sentiment azionario USA**):
1. **CNN API** `https://production.dataviz.cnn.io/index/fearandgreed/graphdata`
   → parser CNN (campo `fear_and_greed.score`), `source: "cnn"`
2. **feargreedmeter.com** `https://feargreedmeter.com/`
   → parser meter (regex sul `<title>` "Fear and Greed Index: N (Label)"),
   `source: "feargreedmeter"` — valore molto vicino al CNN (67 vs 66.7)
3. **feargreedindex.net** `https://feargreedindex.net/api/fear-greed`
   → parser FGI (campi `value` + `label`, `source: "stock"` verificato),
   `source: "feargreedindex"`

Nota: alternative.me (crypto) è stato **scartato** — semanticamente incoerente
con gli indici azionari del progetto. La scelta finale usa **entrambe** le
fonti azionarie trovate (feargreedmeter + feargreedindex) come catena di
fallback, con **priorità a feargreedmeter** (decisione utente: valore più
fedele al CNN, sebbene parsing da `<title>` meno robusto) e feargreedindex
come ultima risorsa (API JSON robusta).

- `run()` usa `fetch_first_success(session, sources, ...)` poi `try_parsers(body, parsers)`
- Output aggiunge `"source"` (es. `"cnn"`, `"feargreedmeter"` o `"feargreedindex"`)
- I parser sono funzioni pure: `parse_cnn(body) -> dict`, `parse_feargreedmeter(body) -> dict` e `parse_feargreedindex(body) -> dict`

## Applicazione a AAII (`aaii_scraper.py`)

Consolidamento del fallback interno esistente (dataChart5 → HTML bars):
- `run()` usa `try_parsers(html, [("data_chart", parse_data_chart), ("html_bars", parse_html_bars)])`
  al posto del `try/except` manuale
- Output aggiunge `"source"` (`"data_chart"` o `"html_bars"`)
- Nessuna nuova fonte (AAII non ha alternative) — il fallback è tra strategie di parse

## Config.yaml

```yaml
# fgi — catena di fonti (primaria + 2 fallback)
fgi:
  config:
    sources:
      - name: cnn
        url: "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
      - name: feargreedmeter
        url: "https://feargreedmeter.com/"
      - name: feargreedindex
        url: "https://feargreedindex.net/api/fear-greed"
```

Mantengo compatibilità: se `sources` non è presente, il modulo usa il default
`[(cnn_url, "cnn")]` (retrocompatibile). Per AAII non serve cambio config
(usa sempre la stessa pagina, cambia solo il parser).

## Report HTML

- La card FGI mostra `source` quando è il fallback (es. `"Fonte: alternative.me"`)
  o sempre (campo meta). Utile per capire l'affidabilità del dato.
- La card AAII mostra `source` (`data_chart` vs `html_bars`).
- Legenda aggiornata con nota sulle sorgenti alternative.

## Test

- `test_fetch_utils.py`:
  - `fetch_first_success`: prima fonte fallisce (mock session) → seconda usata;
    tutte falliscono → RuntimeError
  - `try_parsers`: primo parser fallisce → secondo usato; tutti falliscono → ValueError
- `test_fgi_scraper.py`:
  - `parse_cnn` con body mock CNN → score/rating
  - `parse_feargreedmeter` con body mock feargreedmeter (title) → score/rating
  - `parse_feargreedindex` con body mock feargreedindex → score/rating
  - `run` con `sources` nel config → usa la prima che funziona, `source` nell'output
  - Catena: CNN fallita → feargreedmeter; feargreedmeter fallita → feargreedindex
- `test_aaii_scraper.py`:
  - `run` con HTML che ha solo dataChart5 → `source: "data_chart"`
  - `run` con HTML che ha solo bars → `source: "html_bars"`
  - test esistenti aggiornati per il campo `source`

## File

```
src/fetch_utils.py
src/tests/test_fetch_utils.py
src/scrapers/fgi_scraper.py (modifica)
src/scrapers/aaii_scraper.py (modifica)
src/tests/test_fgi_scraper.py (aggiornamento)
src/tests/test_aaii_scraper.py (aggiornamento)
config.yaml (sources per fgi)
src/report_html.py (card mostra source)
src/tests/test_report_html.py (test source)
```

## Fuori scope

- Fallback per VIX/PCR/Insider/OHLCV (fonti uniche senza alternative reali al momento)
- Scheduler
