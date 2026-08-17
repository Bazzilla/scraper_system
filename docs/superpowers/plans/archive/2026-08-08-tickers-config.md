# Tickers Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere la sezione `tickers:` a `config.yaml` (17 ticker in 2 categorie) con validazione in `config_loader.py` e test.

**Architecture:** Estensione della config top-level esistente. `config.yaml` guadagna una sezione `tickers:` opzionale con categorie → liste di `{symbol, name}`. `config_loader.py` valida la nuova sezione con `_validate_tickers()`, riusando il pattern di `_validate_scraper()`. Nessun cambiamento a orchestrator/consolidator (i moduli OHLCV/indicators arriveranno in un piano separato).

**Tech Stack:** Python, PyYAML, unittest

## Global Constraints

- Sezione `tickers` **opzionale** in config — le esecuzioni senza ticker continuano a funzionare (retrocompatibilità).
- Ogni categoria è una lista **non vuota** di dict con `symbol` (stringa) e `name` (stringa) obbligatori.
- **Symbol univoci** a livello globale (nessun duplicato tra categorie).
- Stile: type hints su tutte le funzioni, snake_case, funzioni pure.
- Eseguire i test da `src/`: `python -m unittest discover -s tests -v`
- **Il progetto NON è un repo git** → i passi "Commit" vanno saltati o sostituiti con una nota (niente `git add`/`git commit`).

---

### Task 1: Validazione sezione `tickers` in config_loader

**Files:**
- Modify: `src/config_loader.py`
- Test: `src/tests/test_config_loader.py` (nuovo — sposta i test `TestConfigLoader` da `test_orchestrator.py`? No: i test restano dove sono; crea un file test dedicato per i ticker: `src/tests/test_tickers_config.py`)

**Interfaces:**
- Consumes: `validate_config(config: dict[str, Any]) -> dict[str, Any]` esistente
- Produces: `_validate_tickers(tickers: Any) -> None` — chiamata da `validate_config` quando `tickers` è presente

- [ ] **Step 1: Scrivi i test falliti in `src/tests/test_tickers_config.py`**

```python
"""Unit tests for the tickers config validation."""

from __future__ import annotations

import unittest

from config_loader import validate_config


def _config_with_tickers(tickers):
    return {"scrapers": {"fgi": {"module": "x", "output_key": "fgi", "schedule": "daily"}}, "tickers": tickers}


class TestTickersValidation(unittest.TestCase):
    def test_valid_tickers(self):
        config = _config_with_tickers(
            {
                "semiconductors": [
                    {"symbol": "AMAT", "name": "Applied Materials"},
                    {"symbol": "LRCX", "name": "Lam Research"},
                ],
                "defense": [{"symbol": "RTX", "name": "RTX"}],
            }
        )
        result = validate_config(config)
        self.assertEqual(result["tickers"]["semiconductors"][0]["symbol"], "AMAT")

    def test_tickers_optional(self):
        config = {"scrapers": {"fgi": {"module": "x", "output_key": "fgi", "schedule": "daily"}}}
        result = validate_config(config)
        self.assertNotIn("tickers", result)

    def test_empty_tickers_mapping_ok(self):
        config = _config_with_tickers({})
        validate_config(config)

    def test_tickers_must_be_mapping(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers(["AMAT"]))

    def test_category_must_be_non_empty_list(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers({"semiconductors": []}))
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers({"semiconductors": "AMAT"}))

    def test_entry_must_be_mapping(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers({"semiconductors": ["AMAT"]}))

    def test_entry_missing_symbol(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers({"semiconductors": [{"name": "Applied Materials"}]}))

    def test_entry_missing_name(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers({"semiconductors": [{"symbol": "AMAT"}]}))

    def test_duplicate_symbol_across_categories(self):
        with self.assertRaises(ValueError):
            validate_config(
                _config_with_tickers(
                    {
                        "semiconductors": [{"symbol": "AMAT", "name": "A"}],
                        "defense": [{"symbol": "AMAT", "name": "B"}],
                    }
                )
            )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Esegui i test per verificare che falliscano**

Run: `cd src && python -m unittest discover -s tests -v`
Expected: FAIL — `ImportError: cannot import name '_validate_tickers'` (o `TypeError`), tutti i test ticker rossi.

- [ ] **Step 3: Implementa la validazione in `src/config_loader.py`**

Aggiungi in coda al file:

```python
def _validate_tickers(tickers: Any) -> None:
    """Validate the optional 'tickers' section (category -> list of {symbol, name})."""
    if not isinstance(tickers, dict):
        raise ValueError("Config 'tickers' must be a mapping")

    seen_symbols: set[str] = set()
    for category, entries in tickers.items():
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"Ticker category {category!r} must be a non-empty list")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"Ticker entry in category {category!r} must be a mapping")
            for field in ("symbol", "name"):
                if field not in entry:
                    raise ValueError(f"Ticker entry in category {category!r} missing required field: {field!r}")
            symbol = entry["symbol"]
            if not isinstance(symbol, str) or not symbol.strip():
                raise ValueError(f"Ticker 'symbol' must be a non-empty string")
            if symbol in seen_symbols:
                raise ValueError(f"Duplicate ticker symbol: {symbol!r}")
            seen_symbols.add(symbol)
```

E aggancia la chiamata dentro `validate_config`, dopo il loop degli scraper (prima di `return config`):

```python
    if "tickers" in config:
        _validate_tickers(config["tickers"])
```

- [ ] **Step 4: Esegui i test per verificare che passino**

Run: `cd src && python -m unittest discover -s tests -v`
Expected: PASS — 31 test esistenti + 10 nuovi ticker (41 totali).

- [ ] **Step 5: (Niente commit — progetto non è un repo git)**

---

### Task 2: Sezione `tickers:` in config.yaml

**Files:**
- Modify: `config.yaml`

**Interfaces:**
- Consumes: niente (dati statici)
- Produces: `tickers:` valido come da Task 1 — 17 ticker, 2 categorie

- [ ] **Step 1: Aggiungi la sezione `tickers:` in `config.yaml`**

Dopo la sezione `scrapers:` (fine file), aggiungi:

```yaml
tickers:
  semiconductors:
    - symbol: AMAT
      name: Applied Materials
    - symbol: LRCX
      name: Lam Research
    - symbol: KLAC
      name: KLA
    - symbol: AVGO
      name: Broadcom
    - symbol: ASML
      name: ASML Holding
    - symbol: TSM
      name: Taiwan Semiconductor
    - symbol: AMD
      name: Advanced Micro Devices
    - symbol: MU
      name: Micron
    - symbol: ADI
      name: Analog Devices
    - symbol: QCOM
      name: Qualcomm
    - symbol: MRVL
      name: Marvell
    - symbol: ENTG
      name: Entegris
  defense:
    - symbol: RTX
      name: RTX
    - symbol: LMT
      name: Lockheed Martin
    - symbol: NOC
      name: Northrop Grumman
    - symbol: GD
      name: General Dynamics
    - symbol: LHX
      name: L3Harris
```

- [ ] **Step 2: Verifica che la config valida**

Run: `cd src && python -c "from config_loader import load_config; c = load_config('../config.yaml'); print(len(c['tickers']['semiconductors']), len(c['tickers']['defense']))"`
Expected: `12 5` (nessuna eccezione)

- [ ] **Step 3: Esegui tutti i test**

Run: `cd src && python -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 4: (Niente commit — progetto non è un repo git)**

---

### Task 3: Documentazione — README e spec

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: niente
- Produces: README aggiornato con la nuova sezione config

- [ ] **Step 1: Aggiorna la sezione Configurazione in `README.md`**

Dopo il blocco di esempio `scrapers:` (riga ~138), aggiungi un sottoblocco per `tickers`:

```markdown
### Sezione `tickers` (lista titoli da monitorare)

Sezione **opzionale** che elenca i titoli per i moduli OHLCV/indicators (futuri),
raggruppati per categoria:

```yaml
tickers:
  semiconductors:
    - symbol: AMAT
      name: Applied Materials
  defense:
    - symbol: RTX
      name: RTX
```

- **Categoria** (es. `semiconductors`, `defense`): lista di ticker dello stesso settore.
- **`symbol`**: simbolo del ticker (obbligatorio, univoco a livello globale).
- **`name`**: nome dell'azienda (obbligatorio).
```

- [ ] **Step 2: Aggiorna la tabella `Stato dei moduli`** (riga ~254) per riflettere la config ticker

| Modulo | Stato | Note |
|--------|-------|------|
| Config `tickers` | ✅ Funzionante | 17 ticker in 2 categorie (semiconductors, defense), validato da `config_loader` |

- [ ] **Step 3: Aggiorna la struttura del progetto** (riga ~52) con `docs/`

```
├── docs/
│   └── superpowers/
│       ├── specs/2026-08-08-tickers-config-design.md
│       └── plans/2026-08-08-tickers-config.md
```

- [ ] **Step 4: (Niente commit — progetto non è un repo git)**
