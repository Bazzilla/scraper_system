# Validità temporale dinamica nel report HTML — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il report HTML mostra la validità temporale reale di ogni dato (badge fresh/stale + testo età "aggiornato X fa · scade tra Y" / "scaduto da X") calcolata client-side via JavaScript rispetto alla data odierna.

**Architecture:** Python inietta attributi `data-fetched-at` + `data-stale-hours` nelle card indicatori di mercato e nelle righe delle tabelle ticker; uno script JS esteso al blocco esistente (`_SCRIPT`) ricalcola età e stato al caricamento e aggiorna badge + testo. Il badge server-side resta come fallback se JS è disabilitato.

**Tech Stack:** Python 3.10+ (venv `.venv/bin/python`), unittest, HTML/CSS/JS vanilla (ES5, coerente con lo script theme-toggle esistente).

## Global Constraints

- Tutto va eseguito con `.venv/bin/python` (PEP 668, niente install globale)
- Test da `src/`: `cd src && ../.venv/bin/python -m unittest discover -s tests`
- Naming: snake_case per funzioni Python; il JS usa `var`/`function` (ES5, come `_SCRIPT` esistente)
- Il report deve restare una pagina statica self-contained (nessuna dipendenza esterna)
- La matrice indicatori (`render_indicator_matrix`) NON viene toccata
- Le card di errore (`_error_card`) NON ricevono `data-*` (nessun timestamp)
- Test esistenti devono restare verdi (suite 224 test)

---

### Task 1: Helper Python `_age_attrs`

**Files:**
- Modify: `src/report_html.py` (aggiungere helper dopo `_badge`, ~riga 318)
- Test: `src/tests/test_report_html.py` (nuova classe `TestAgeAttrs`)

**Interfaces:**
- Consumes: niente (funzione autonoma)
- Produces: `_age_attrs(fetched_at: str | None, stale_after_hours: float | None) -> str` — ritorna ` data-fetched-at="<iso>" data-stale-hours="<n>"` (con spazi iniziali) oppure stringa vuota se `fetched_at` è None/vuoto o `stale_after_hours` è None. I valori vanno escapati con `html_mod.escape` per l'ISO.

- [ ] **Step 1: Write the failing test**

Aggiungere in `src/tests/test_report_html.py` (dopo la classe `TestRenderSections` o in fondo, prima di `if __name__`):

```python
class TestAgeAttrs(unittest.TestCase):
    def test_returns_attrs_with_valid_timestamp(self):
        attrs = _age_attrs("2026-08-12T14:30:06+00:00", 24)
        self.assertIn('data-fetched-at="2026-08-12T14:30:06+00:00"', attrs)
        self.assertIn('data-stale-hours="24"', attrs)

    def test_returns_empty_without_fetched_at(self):
        self.assertEqual(_age_attrs(None, 24), "")
        self.assertEqual(_age_attrs("", 24), "")

    def test_returns_empty_without_stale_hours(self):
        self.assertEqual(_age_attrs("2026-08-12T14:30:06+00:00", None), "")

    def test_escapes_iso_value(self):
        attrs = _age_attrs('2026-08-12T14:30:06+00:00" onclick="x', 24)
        self.assertNotIn('" onclick="', attrs)
```

Aggiornare l'import in cima al file:

```python
from report_html import (
    _age_attrs,
    build_page,
    ...
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_report_html.TestAgeAttrs -v`
Expected: FAIL con `ImportError: cannot import name '_age_attrs'`

- [ ] **Step 3: Write minimal implementation**

In `src/report_html.py`, dopo la funzione `_badge` (riga ~318):

```python
def _age_attrs(fetched_at: str | None, stale_after_hours: float | None) -> str:
    """Return HTML data-* attributes for client-side age computation.

    Returns a string like `` data-fetched-at="..." data-stale-hours="..."``
    (leading space included) or an empty string when the timestamp or the
    validity window is missing.
    """
    if not fetched_at or stale_after_hours is None:
        return ""
    iso = html_mod.escape(fetched_at)
    return f' data-fetched-at="{iso}" data-stale-hours="{stale_after_hours}"'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_report_html.TestAgeAttrs -v`
Expected: PASS (4 test)

- [ ] **Step 5: Commit**

```bash
git add src/report_html.py src/tests/test_report_html.py
git commit -m "feat: add _age_attrs helper for client-side data age"
```

---

### Task 2: Attributi `data-*` nelle card indicatori di mercato

**Files:**
- Modify: `src/report_html.py` — `render_market_cards` (righe 321-484)
- Test: `src/tests/test_report_html.py` (classe `TestRenderSections`)

**Interfaces:**
- Consumes: `_age_attrs(fetched_at, stale_after_hours)` dal Task 1
- Produces: card HTML con attributi `data-fetched-at`/`data-stale-hours` sulla `<div class="card">` per: FGI, VIX, PCR, breadth (pct_sma), insider, AAII, NAAIM. Le card di errore e la nota VIX TS (dentro la card VIX) NON ricevono attributi.

- [ ] **Step 1: Write the failing test**

Aggiungere in `src/tests/test_report_html.py` nella classe `TestRenderSections`:

```python
    def test_market_cards_include_age_attrs(self):
        html = render_market_cards(_sample_data())
        self.assertIn('data-fetched-at="2026-08-12T14:29:42+00:00"', html)  # fgi
        self.assertIn('data-stale-hours="24"', html)  # fgi
        self.assertIn('data-fetched-at="2026-08-12T14:29:43+00:00"', html)  # aaii
        self.assertIn('data-stale-hours="168"', html)  # aaii

    def test_error_card_has_no_age_attrs(self):
        data = _sample_data()
        data["fgi"] = {"status": "error", "error": "All sources failed"}
        html = render_market_cards(data)
        # La card di errore non ha timestamp → nessun data-fetched-at per fgi
        self.assertNotIn('data-fetched-at="2026-08-12T14:29:42+00:00"', html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_report_html.TestRenderSections.test_market_cards_include_age_attrs tests.test_report_html.TestRenderSections.test_error_card_has_no_age_attrs -v`
Expected: FAIL (attributi assenti nell'HTML)

- [ ] **Step 3: Write minimal implementation**

In `src/report_html.py`, modificare ogni card NON-error in `render_market_cards` aggiungendo `{_age_attrs(...)}` alla `<div class="card">`:

1. **FGI** (riga 371): `<div class="card">` → `<div class="card"{_age_attrs(fgi.get("fetched_at"), fgi.get("stale_after_hours"))}>`
2. **VIX** (riga 391): `<div class="card">` → `<div class="card"{_age_attrs(vix.get("fetched_at"), vix.get("stale_after_hours"))}>` (usa `vix`, non `vix_ts` — la VIX TS è solo una nota dentro la card)
3. **PCR** (riga 408): `<div class="card">` → `<div class="card"{_age_attrs(pcr.get("fetched_at"), pcr.get("stale_after_hours"))}>`
4. **Breadth** (riga 430): `<div class="card">` → `<div class="card"{_age_attrs(pct_sma.get("fetched_at"), pct_sma.get("stale_after_hours"))}>`
5. **Insider** (riga 447): `<div class="card">` → `<div class="card"{_age_attrs(insider.get("fetched_at"), insider.get("stale_after_hours"))}>`
6. **AAII** (riga 463): `<div class="card">` → `<div class="card"{_age_attrs(aaii.get("fetched_at"), aaii.get("stale_after_hours"))}>`
7. **NAAIM** (riga 478): `<div class="card">` → `<div class="card"{_age_attrs(naaim.get("fetched_at"), naaim.get("stale_after_hours"))}>`

Le card di errore (`_error_card`) restano invariate.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_report_html.TestRenderSections -v`
Expected: PASS (tutti i test della classe, inclusi i 2 nuovi)

- [ ] **Step 5: Commit**

```bash
git add src/report_html.py src/tests/test_report_html.py
git commit -m "feat: inject data-age attributes into market cards"
```

---

### Task 3: Attributi `data-*` nelle righe delle tabelle ticker

**Files:**
- Modify: `src/report_html.py` — `render_ticker_table` (righe 500-531)
- Test: `src/tests/test_report_html.py` (classe `TestRenderSections`)

**Interfaces:**
- Consumes: `_age_attrs(fetched_at, stale_after_hours)` dal Task 1
- Produces: righe `<tr>` con attributi `data-fetched-at`/`data-stale-hours` per ogni ticker

- [ ] **Step 1: Write the failing test**

Aggiungere in `src/tests/test_report_html.py` nella classe `TestRenderSections`:

```python
    def test_ticker_rows_include_age_attrs(self):
        data = _sample_data()
        entries = data["indicators"]["semiconductors"]
        html = render_ticker_table("semiconductors", entries)
        self.assertIn('data-fetched-at="2026-08-12T14:30:06+00:00"', html)
        self.assertIn('data-stale-hours="24"', html)

    def test_ticker_row_without_fetched_at_has_no_attrs(self):
        data = _sample_data()
        entries = data["indicators"]["semiconductors"]
        no_ts = dict(entries["AMAT"], fetched_at=None)
        html = render_ticker_table("semiconductors", {"AMAT": no_ts})
        self.assertNotIn("data-fetched-at=", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_report_html.TestRenderSections.test_ticker_rows_include_age_attrs tests.test_report_html.TestRenderSections.test_ticker_row_without_fetched_at_has_no_attrs -v`
Expected: FAIL (attributi assenti)

- [ ] **Step 3: Write minimal implementation**

In `src/report_html.py`, `render_ticker_table`, modificare la riga (riga 511):

```python
        rows.append(
            f"<tr{_age_attrs(ind.get('fetched_at'), ind.get('stale_after_hours'))}>"
            f'<td><span class="ticker">{html_mod.escape(symbol)}</span>'
            ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_report_html.TestRenderSections -v`
Expected: PASS (tutti i test della classe)

- [ ] **Step 5: Commit**

```bash
git add src/report_html.py src/tests/test_report_html.py
git commit -m "feat: inject data-age attributes into ticker table rows"
```

---

### Task 4: CSS `.age` + script JS di ricalcolo età

**Files:**
- Modify: `src/report_html.py` — `_CSS` (aggiungere classe `.age`), `_SCRIPT` (estendere con il ricalcolo età)
- Test: `src/tests/test_report_html.py` (classe `TestRenderSections` o nuova `TestAgeScript`)

**Interfaces:**
- Consumes: attributi `data-fetched-at`/`data-stale-hours` iniettati nei Task 2-3
- Produces: al caricamento, per ogni elemento con `data-fetched-at`: badge `<span class="badge age-badge fresh|stale">` e testo `<span class="age">aggiornato X fa · scade tra Y</span>` o `<span class="age">scaduto da X</span>`

- [ ] **Step 1: Write the failing test**

Aggiungere in `src/tests/test_report_html.py`:

```python
class TestAgeScript(unittest.TestCase):
    def test_script_contains_age_logic(self):
        from report_html import _SCRIPT
        self.assertIn("data-fetched-at", _SCRIPT)
        self.assertIn("data-stale-hours", _SCRIPT)
        self.assertIn("scaduto da", _SCRIPT)
        self.assertIn("aggiornato", _SCRIPT)
        self.assertIn("age-badge", _SCRIPT)

    def test_css_contains_age_class(self):
        from report_html import _CSS
        self.assertIn(".age", _CSS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_report_html.TestAgeScript -v`
Expected: FAIL (script e CSS non contengono ancora la logica età)

- [ ] **Step 3: Write minimal implementation**

**CSS** — in `_CSS`, dopo la riga `.badge.stale` (riga 45), aggiungere:

```
.age { color: var(--muted); font-size: 0.75rem; display: block; margin-top: 2px; }
.badge.age-badge { margin-left: 8px; }
```

**JS** — sostituire l'intero `_SCRIPT` con:

```python
_SCRIPT = """\
<script>
(function () {
  var saved = localStorage.getItem("report-theme");
  var theme = saved || "dark";
  document.documentElement.setAttribute("data-theme", theme);
  var btn = document.getElementById("theme-toggle");
  btn.textContent = theme === "dark" ? "☀️ Light" : "🌙 Dark";
  btn.addEventListener("click", function () {
    var next = theme === "dark" ? "light" : "dark";
    theme = next;
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("report-theme", next);
    btn.textContent = next === "dark" ? "☀️ Light" : "🌙 Dark";
  });

  function fmtAge(ms) {
    var min = Math.floor(ms / 60000);
    if (min < 60) return min + "min fa";
    var h = Math.floor(min / 60);
    if (h < 24) return h + "h fa";
    return Math.floor(h / 24) + "g fa";
  }

  function fmtRemaining(ms) {
    var min = Math.ceil(ms / 60000);
    if (min < 60) return "tra " + min + "min";
    var h = Math.ceil(min / 60);
    if (h < 24) return "tra " + h + "h";
    return "tra " + Math.ceil(h / 24) + "g";
  }

  var els = document.querySelectorAll("[data-fetched-at]");
  for (var i = 0; i < els.length; i++) {
    var el = els[i];
    var fetched = Date.parse(el.getAttribute("data-fetched-at"));
    if (isNaN(fetched)) continue;
    var staleHours = parseFloat(el.getAttribute("data-stale-hours")) || 0;
    var ageMs = Date.now() - fetched;
    var staleMs = staleHours * 3600000;
    var isStale = ageMs > staleMs;
    var status = isStale ? "stale" : "fresh";
    var text = isStale
      ? "scaduto da " + fmtAge(ageMs - staleMs)
      : "aggiornato " + fmtAge(ageMs) + " · " + fmtRemaining(staleMs - ageMs);

    var badge = document.createElement("span");
    badge.className = "badge age-badge " + status;
    badge.textContent = status;
    var value = el.querySelector(".value");
    if (value) {
      value.parentNode.insertBefore(badge, value.nextSibling);
    } else {
      var firstCell = el.querySelector("td:first-child");
      if (firstCell) firstCell.appendChild(badge);
    }

    var age = document.createElement("span");
    age.className = "age";
    age.textContent = text;
    var meta = el.querySelector(".meta");
    if (meta) {
      meta.appendChild(age);
    } else {
      var lastCell = el.querySelector("td:last-child");
      if (lastCell) lastCell.appendChild(age);
    }
  }
})();
</script>
"""
```

Nota: il JS è ES5 (var/function) per coerenza con lo script theme-toggle esistente. Per le card il badge va dopo `.value`; per le righe ticker il badge va nella prima cella e il testo età nell'ultima cella (colonna "Aggiornato").

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && ../.venv/bin/python -m unittest tests.test_report_html.TestAgeScript -v`
Expected: PASS (2 test)

- [ ] **Step 5: Commit**

```bash
git add src/report_html.py src/tests/test_report_html.py
git commit -m "feat: client-side data-age recalculation in report JS"
```

---

### Task 5: Verifica finale e suite completa

**Files:**
- Nessun file nuovo — verifica end-to-end

**Interfaces:**
- Consumes: tutti i Task 1-4

- [ ] **Step 1: Run the full test suite**

Run: `cd src && ../.venv/bin/python -m unittest discover -s tests`
Expected: OK — 224 test esistenti + 8 nuovi (4 TestAgeAttrs + 2 TestRenderSections card + 2 TestRenderSections ticker + 2 TestAgeScript) = 232 test, tutti verdi

- [ ] **Step 2: Generate the report and verify manually**

Run: `./.venv/bin/python run.py --report-only`
Expected: `output/report.html` rigenerato senza errori

- [ ] **Step 3: Verify the HTML contains the new attributes and script**

Run: `grep -c 'data-fetched-at' output/report.html`
Expected: ≥ 9 (7 card + almeno 1 riga ticker + 1 occorrenza nello script)

- [ ] **Step 4: Open the report in a browser and check**

Aprire `output/report.html`:
- Ogni card indicatore mostra un badge `fresh` (verde) o `stale` (rosso) accanto al valore
- Ogni card mostra il testo "aggiornato X fa · scade tra Y" o "scaduto da X" sotto il meta
- Ogni riga ticker mostra il badge e il testo età nella colonna Aggiornato
- Il toggle dark/light continua a funzionare

- [ ] **Step 5: Commit any leftover changes**

```bash
git status
git add -A
git commit -m "chore: verify data-age feature end-to-end"
```

(Se non ci sono modifiche pendenti, saltare il commit.)