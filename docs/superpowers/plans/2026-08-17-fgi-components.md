# Componenti FGI (7 sotto-indicatori) dal payload CNN — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estrarre i 7 sotto-indicatori del Fear & Greed Index dal payload dell'API CNN e mostrarli come informazione aggiuntiva (mini-griglia nella card FGI del report HTML + nested in `fgi.fgi_components` nell'output). Nessun impatto sullo scoring.

**Architecture:** `parse_components()` nuovo in `fgi_scraper.py` mappa le 7 chiavi CNN in chiavi snake_case progetto; `parse_cnn`/`build_result`/`run` propagano i componenti solo quando la fonte vincente è `cnn`; `render_market_cards` mostra la mini-griglia nella card FGI. Fonte non-CNN → chiave assente, nessun fallback debole.

**Tech Stack:** Python 3.10+ (venv `.venv/bin/python`), unittest, HTML/CSS vanilla (nessun JS nuovo per questa feature).

## Global Constraints

- Tutto va eseguito con `.venv/bin/python` (PEP 668, niente install globale)
- Test da `src/`: `cd src && ../.venv/bin/python -m unittest discover -s tests`
- Naming: snake_case per chiavi e funzioni Python; rating lowercase (extreme fear / fear / neutral / greed / extreme greed)
- I 7 sotto-indicatori NON entrano nello scoring/segnale (`compute_signal`, gate FGI) — solo informazione
- Fonte non-CNN → `fgi_components` ASSENTE (nessuna chiave vuota, nessun placeholder)
- Componente malformato/mancante nel payload → componente saltato (fail-soft sul singolo), gli altri restano
- `config.yaml`, `indicator_registry.yaml`, `manual_overrides.yaml` NON modificati
- Test esistenti devono restare verdi (suite 234 test)

---

### Task 1: Funzione `parse_components` in `fgi_scraper.py`

**Files:**
- Modify: `src/scrapers/fgi_scraper.py` (aggiungere dopo `parse_score`, ~riga 81)
- Test: `src/tests/test_fgi_scraper.py` (nuova classe `TestParseComponents`)

**Interfaces:**
- Consumes: niente (funzione autonoma, usa solo il payload dict già parsato)
- Produces: `parse_components(payload: dict[str, Any]) -> dict[str, dict[str, Any]]` — mappa le 7 chiavi API CNN in chiavi progetto, ognuna con `{"score": float, "rating": str}`. Salta chiavi mancanti/malformate. Restituisce `{}` se nessun componente valido.

- [ ] **Step 1: Write the failing test**

Aggiungere in `src/tests/test_fgi_scraper.py` (importare `parse_components`):

```python
class TestParseComponents(unittest.TestCase):
    _PAYLOAD = {
        "market_momentum_sp500": {"score": 74.6, "rating": "greed"},
        "stock_price_strength": {"score": 28.6, "rating": "fear"},
        "stock_price_breadth": {"score": 57.8, "rating": "greed"},
        "put_call_options": {"score": 66.4, "rating": "greed"},
        "market_volatility_vix": {"score": 50.0, "rating": "neutral"},
        "junk_bond_demand": {"score": 98.6, "rating": "extreme greed"},
        "safe_haven_demand": {"score": 78.8, "rating": "extreme greed"},
    }

    def test_parses_all_seven_components(self):
        result = parse_components(self._PAYLOAD)
        self.assertEqual(len(result), 7)
        self.assertEqual(result["market_momentum"], {"score": 74.6, "rating": "greed"})
        self.assertEqual(result["stock_price_strength"], {"score": 28.6, "rating": "fear"})
        self.assertEqual(result["stock_price_breadth"], {"score": 57.8, "rating": "greed"})
        self.assertEqual(result["put_call_options"], {"score": 66.4, "rating": "greed"})
        self.assertEqual(result["market_volatility"], {"score": 50.0, "rating": "neutral"})
        self.assertEqual(result["junk_bond_demand"], {"score": 98.6, "rating": "extreme greed"})
        self.assertEqual(result["safe_haven_demand"], {"score": 78.8, "rating": "extreme greed"})

    def test_skips_missing_component(self):
        payload = dict(self._PAYLOAD)
        del payload["market_volatility_vix"]
        result = parse_components(payload)
        self.assertEqual(len(result), 6)
        self.assertNotIn("market_volatility", result)

    def test_skips_malformed_component(self):
        payload = dict(self._PAYLOAD)
        payload["junk_bond_demand"] = {"score": "not-a-number"}  # score non float
        result = parse_components(payload)
        self.assertNotIn("junk_bond_demand", result)
        self.assertIn("market_momentum", result)

    def test_returns_empty_when_no_valid_components(self):
        self.assertEqual(parse_components({}), {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_fgi_scraper.TestParseComponents -v`
Expected: FAIL con `ImportError: cannot import name 'parse_components'`

- [ ] **Step 3: Write minimal implementation**

In `src/scrapers/fgi_scraper.py`, dopo `parse_score`:

```python
# Chiavi API CNN → chiavi progetto (snake_case). Ordinate come nel payload CNN.
COMPONENT_KEYS: tuple[tuple[str, str], ...] = (
    ("market_momentum_sp500", "market_momentum"),
    ("stock_price_strength", "stock_price_strength"),
    ("stock_price_breadth", "stock_price_breadth"),
    ("put_call_options", "put_call_options"),
    ("market_volatility_vix", "market_volatility"),
    ("junk_bond_demand", "junk_bond_demand"),
    ("safe_haven_demand", "safe_haven_demand"),
)


def parse_components(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract the 7 FGI sub-indicators from the CNN API payload.

    Each component is mapped to a snake_case project key and carries
    ``score`` (0-100) and ``rating`` (label). Fail-soft per component: a
    missing or malformed key is skipped, the others remain.

    Returns:
        dict mapping project key → {"score": float, "rating": str}. Empty
        dict when no component is valid.
    """
    result: dict[str, dict[str, Any]] = {}
    for api_key, project_key in COMPONENT_KEYS:
        raw = payload.get(api_key)
        if not isinstance(raw, dict):
            continue
        try:
            score = float(raw["score"])
            rating = str(raw["rating"]).strip().lower()
        except (KeyError, TypeError, ValueError):
            continue
        if not rating:
            continue
        result[project_key] = {"score": score, "rating": rating}
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_fgi_scraper.TestParseComponents -v`
Expected: PASS (4 test)

- [ ] **Step 5: Commit**

```bash
git add src/scrapers/fgi_scraper.py src/tests/test_fgi_scraper.py
git commit -m "feat: add parse_components for FGI 7 sub-indicators"
```

---

### Task 2: Propagare i componenti in `parse_cnn`, `build_result`, `run`

**Files:**
- Modify: `src/scrapers/fgi_scraper.py` — `parse_cnn` (righe 84-86), `build_result` (righe 138-147), `run` (righe 150-189)
- Test: `src/tests/test_fgi_scraper.py`

**Interfaces:**
- Consumes: `parse_components(payload) -> dict` dal Task 1
- Produces: 
  - `parse_cnn(body) -> dict` — ora include anche `fgi_components: {...}` (chiave presente SOLO se `parse_components` restituisce almeno un componente; altrimenti assente)
  - `build_result(score, zone, fetched_at, fgi_components=None) -> dict` — include `fgi_components` nel risultato solo se non-None
  - `run(config) -> dict` — passa i componenti a `build_result` solo quando `source == "cnn"`

- [ ] **Step 1: Write the failing test**

Aggiungere in `src/tests/test_fgi_scraper.py`:

```python
class TestParseCnnComponents(unittest.TestCase):
    _BODY = json.dumps({
        "fear_and_greed": {"score": 66.7, "rating": "greed"},
        "market_momentum_sp500": {"score": 74.6, "rating": "greed"},
        "stock_price_strength": {"score": 28.6, "rating": "fear"},
        "stock_price_breadth": {"score": 57.8, "rating": "greed"},
        "put_call_options": {"score": 66.4, "rating": "greed"},
        "market_volatility_vix": {"score": 50.0, "rating": "neutral"},
        "junk_bond_demand": {"score": 98.6, "rating": "extreme greed"},
        "safe_haven_demand": {"score": 78.8, "rating": "extreme greed"},
    })

    def test_parse_cnn_includes_components(self):
        result = parse_cnn(self._BODY)
        self.assertEqual(result["score"], 66.7)
        self.assertEqual(result["zone"], "greed")
        self.assertEqual(len(result["fgi_components"]), 7)
        self.assertEqual(result["fgi_components"]["market_momentum"], {"score": 74.6, "rating": "greed"})

    def test_parse_cnn_omits_components_when_absent(self):
        body = '{"fear_and_greed": {"score": 66.7, "rating": "greed"}}'
        result = parse_cnn(body)
        self.assertNotIn("fgi_components", result)


class TestBuildResultComponents(unittest.TestCase):
    def test_includes_components_when_given(self):
        comps = {"market_momentum": {"score": 74.6, "rating": "greed"}}
        result = build_result(66.7, "greed", "2026-08-07T08:00:00+00:00", fgi_components=comps)
        self.assertEqual(result["fgi_components"], comps)

    def test_omits_components_when_none(self):
        result = build_result(66.7, "greed", "2026-08-07T08:00:00+00:00")
        self.assertNotIn("fgi_components", result)


class TestRunComponents(unittest.TestCase):
    def test_run_cnn_includes_components(self):
        body = json.dumps({
            "fear_and_greed": {"score": 66.7, "rating": "greed"},
            "market_momentum_sp500": {"score": 74.6, "rating": "greed"},
        })
        with mock.patch(
            "scrapers.fgi_scraper.fetch_first_success",
            return_value=(body, "cnn"),
        ):
            result = run()
        self.assertEqual(result["source"], "cnn")
        self.assertIn("fgi_components", result)
        self.assertEqual(result["fgi_components"]["market_momentum"], {"score": 74.6, "rating": "greed"})

    def test_run_fallback_omits_components(self):
        body = '{"value":71,"label":"Greed","source":"stock"}'
        with mock.patch(
            "scrapers.fgi_scraper.fetch_first_success",
            return_value=(body, "feargreedindex"),
        ):
            result = run()
        self.assertEqual(result["source"], "feargreedindex")
        self.assertNotIn("fgi_components", result)
```

Nota: aggiungere `import json` in cima a `test_fgi_scraper.py` se non già presente.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_fgi_scraper.TestParseCnnComponents tests.test_fgi_scraper.TestBuildResultComponents tests.test_fgi_scraper.TestRunComponents -v`
Expected: FAIL (fgi_components assente)

- [ ] **Step 3: Write minimal implementation**

**`parse_cnn`** (righe 84-86) — sostituire:

```python
def parse_cnn(payload: str) -> dict[str, Any]:
    """Parse the CNN API JSON payload (primary source)."""
    data = parse_score(json.loads(payload))
    components = parse_components(json.loads(payload))
    if components:
        data["fgi_components"] = components
    return data
```

Nota: per evitare di parsare il JSON due volte, si può fare:

```python
def parse_cnn(payload: str) -> dict[str, Any]:
    """Parse the CNN API JSON payload (primary source)."""
    raw = json.loads(payload)
    data = parse_score(raw)
    components = parse_components(raw)
    if components:
        data["fgi_components"] = components
    return data
```

**`build_result`** (righe 138-147) — aggiungere parametro:

```python
def build_result(
    score: float,
    zone: str,
    fetched_at: str,
    fgi_components: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the output dict in the file.json format."""
    result = {
        "score": score,
        "zone": zone,
        "fetched_at": fetched_at,
        "frequency": FREQUENCY,
        "stale_after_hours": DEFAULT_STALE_AFTER_HOURS,
        "status": "fresh",
    }
    if fgi_components:
        result["fgi_components"] = fgi_components
    return result
```

**`run`** (righe 185-189) — passare i componenti quando fonte cnn:

```python
    parser_list = [(source, parsers[source])]
    data, _ = try_parsers(body, parser_list)
    components = data.get("fgi_components") if source == "cnn" else None
    result = build_result(data["score"], data["zone"], _now_iso(), fgi_components=components)
    result["source"] = source
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_fgi_scraper -v`
Expected: PASS (tutta la classe, inclusi i nuovi test)

- [ ] **Step 5: Commit**

```bash
git add src/scrapers/fgi_scraper.py src/tests/test_fgi_scraper.py
git commit -m "feat: propagate FGI sub-indicators from CNN payload"
```

---

### Task 3: Mini-griglia componenti FGI nella card del report

**Files:**
- Modify: `src/report_html.py` — `_CSS` (aggiungere stile mini-griglia), `render_market_cards` (card FGI, righe ~370-385)
- Test: `src/tests/test_report_html.py` (classe `TestRenderSections`)

**Interfaces:**
- Consumes: `fgi.fgi_components` dal JSON di output (Task 2), classi CSS `sema` esistenti (fear/greed/extreme_fear/extreme_greed/neutral)
- Produces: card FGI con mini-griglia `<div class="fgi-components">` quando `fgi_components` presente; card invariata quando assente

- [ ] **Step 1: Write the failing test**

Aggiungere in `src/tests/test_report_html.py` nella classe `TestRenderSections`:

```python
    def test_fgi_card_shows_components_grid(self):
        data = _sample_data()
        data["fgi"]["fgi_components"] = {
            "market_momentum": {"score": 74.6, "rating": "greed"},
            "stock_price_strength": {"score": 28.6, "rating": "fear"},
        }
        html = render_market_cards(data)
        self.assertIn("fgi-components", html)
        self.assertIn("Market Momentum", html)
        self.assertIn("74.6", html)
        self.assertIn("Stock Price Strength", html)
        self.assertIn("28.6", html)

    def test_fgi_card_without_components_no_grid(self):
        html = render_market_cards(_sample_data())
        self.assertNotIn("fgi-components", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_report_html.TestRenderSections.test_fgi_card_shows_components_grid tests.test_report_html.TestRenderSections.test_fgi_card_without_components_no_grid -v`
Expected: FAIL (mini-griglia assente)

- [ ] **Step 3: Write minimal implementation**

**CSS** — in `_CSS`, dopo la regola `.badge.age-badge` (o in una zona logica vicino a `.card`), aggiungere:

```
.fgi-components { margin-top: 10px; border-top: 1px solid var(--border);
        padding-top: 8px; display: grid; gap: 4px; font-size: 0.8rem; }
.fgi-components .comp { display: flex; justify-content: space-between;
        align-items: center; gap: 8px; }
.fgi-components .comp-name { color: var(--muted); }
```

**Helper** — aggiungere una funzione per il badge rating (dopo `_badge`, vicino alle altre helper):

```python
def _fgi_rating_badge(rating: str) -> str:
    """Render a FGI component rating badge (fear/greed/neutral...)."""
    cls = rating.strip().lower().replace(" ", "_")
    return f'<span class="sema {cls}">{html_mod.escape(rating)}</span>'
```

**Card FGI** — in `render_market_cards`, dopo la creazione di `zone_badge` e prima di `parts.append(...)`, aggiungere la mini-griglia:

```python
        fgi_components = fgi.get("fgi_components")
        if fgi_components:
            comp_rows = []
            for key, comp in fgi_components.items():
                name = key.replace("_", " ").title()
                score = comp.get("score")
                rating = str(comp.get("rating", ""))
                comp_rows.append(
                    '<div class="comp"><span class="comp-name">'
                    f"{html_mod.escape(name)}</span>"
                    f"<span>{fmt(score)} {_fgi_rating_badge(rating)}</span></div>"
                )
            components_html = f'<div class="fgi-components">{"".join(comp_rows)}</div>'
        else:
            components_html = ""
```

Poi nella card FGI, aggiungere `{components_html}` prima di `</div>` finale:

```python
        parts.append(
            f'<div class="card"{_age_attrs(fgi.get("fetched_at"), fgi.get("stale_after_hours"))}><div class="label">CNN Fear &amp; Greed</div>'
            f'<div class="value">{fmt(fgi_score)}</div>{zone_badge}'
            f'<div class="meta">Aggiornato: {format_iso_dt(fgi.get("fetched_at"))}{source_html}</div>'
            f'{components_html}{_origin_html(fgi)}</div>'
        )
```

Nota: i nomi vengono da `key.replace("_", " ").title()` → "Market Momentum", "Stock Price Strength", ecc. (coerente con la pagina CNN).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_report_html.TestRenderSections -v`
Expected: PASS (tutti i test della classe, inclusi i 2 nuovi)

- [ ] **Step 5: Commit**

```bash
git add src/report_html.py src/tests/test_report_html.py
git commit -m "feat: render FGI sub-indicators grid in report card"
```

---

### Task 4: Verifica finale e suite completa

**Files:**
- Nessun file nuovo — verifica end-to-end

**Interfaces:**
- Consumes: tutti i Task 1-3

- [ ] **Step 1: Run the full test suite**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests`
Expected: OK — 234 test esistenti + nuovi (4 TestParseComponents + 2 TestParseCnnComponents + 2 TestBuildResultComponents + 2 TestRunComponents + 2 TestRenderSections) = 246 test, tutti verdi

- [ ] **Step 2: Generate the report and verify manually**

Run: `./.venv/bin/python run.py`
Expected: orchestrazione + report rigenerati senza errori

- [ ] **Step 3: Verify the output JSON contains fgi_components**

Run: `grep -c 'fgi_components' output/output.json`
Expected: ≥ 1 (se la fonte CNN ha risposto; se è andata in fallback, verificare che la chiave sia assente e che non ci siano errori)

- [ ] **Step 4: Open the report in a browser and check**

Aprire `output/report.html`:
- La card CNN Fear & Greed mostra la mini-griglia con i 7 componenti (nome + score + rating colorato)
- Se la fonte non era CNN, la card è identica a prima (nessuna mini-griglia)
- Il badge età dinamica e il toggle dark/light continuano a funzionare

- [ ] **Step 5: Commit any leftover changes**

```bash
git status
git add -A
git commit -m "chore: verify FGI components feature end-to-end"
```

(Se non ci sono modifiche pendenti, saltare il commit.)