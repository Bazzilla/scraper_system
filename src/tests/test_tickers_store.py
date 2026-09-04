"""Unit tests for the tickers store (config.yaml read/backup/save)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import yaml

from config_loader import normalize_tickers
from tickers_page import render_tickers_page
from tickers_store import (
    backup_config,
    dump_tickers_block,
    export_tickers,
    import_tickers,
    load_tickers,
    save_tickers,
)

CONFIG_TEXT = (
    "# commento top-level da preservare\n"
    "output:\n"
    "  json_path: output/output.json\n"
    "scrapers:\n"
    "  fgi:\n"
    "    module: scrapers.fgi_scraper\n"
    "    output_key: fgi\n"
    "    schedule: daily\n"
    "tickers:\n"
    "  # vecchio commento interno (blocco sostituito dal salvataggio)\n"
    "  semiconductors:\n"
    "    - symbol: AMAT\n"
    "      name: Applied Materials\n"
    "      quality_tier: core\n"
)

NEW_TICKERS = {
    "defense": [
        {"symbol": "BAH", "name": "Booz Allen Hamilton", "quality_tier": "secondary"},
        {"symbol": "LDOS", "name": "Leidos", "quality_tier": "opportunistic"},
    ],
    "semiconductors": [
        {"symbol": "AMAT", "name": "Applied Materials", "quality_tier": "core"},
        {"symbol": "NVDA", "name": "NVIDIA"},
    ],
}


def _write_config(tmp: str, text: str = CONFIG_TEXT) -> Path:
    path = Path(tmp) / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


class TestLoadTickers(unittest.TestCase):
    def test_loads_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp)
            tickers = load_tickers(str(path))
        self.assertIn("semiconductors", tickers)
        self.assertEqual(tickers["semiconductors"][0]["symbol"], "AMAT")

    def test_load_missing_section_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, "output:\n  json_path: x.json\n")
            self.assertEqual(load_tickers(str(path)), {})


class TestBackupConfig(unittest.TestCase):
    def test_backup_named_with_epoch_and_copies_content(self):
        now = datetime(2026, 8, 20, 12, 30, 45, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp)
            backup = backup_config(str(path), now=now)
            expected_stamp = int(now.timestamp())
            self.assertEqual(backup.name, f"config-{expected_stamp}.yaml")
            self.assertEqual(backup.parent.name, "backups")
            self.assertEqual(
                backup.read_text(encoding="utf-8"),
                path.read_text(encoding="utf-8"),
            )


class TestDumpTickersBlock(unittest.TestCase):
    def test_block_is_valid_yaml_with_metadata(self):
        block = dump_tickers_block(NEW_TICKERS)
        parsed = yaml.safe_load(block)
        self.assertEqual(parsed["tickers"], NEW_TICKERS)
        self.assertIn("quality_tier: secondary", block)

    def test_block_quotes_special_characters(self):
        block = dump_tickers_block({"cat": [{"symbol": "X", "name": "A: B #C"}]})
        parsed = yaml.safe_load(block)
        self.assertEqual(parsed["tickers"]["cat"][0]["name"], "A: B #C")


class TestSaveTickers(unittest.TestCase):
    def test_save_splices_block_and_preserves_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp)
            backup = save_tickers(str(path), NEW_TICKERS)
            text = path.read_text(encoding="utf-8")
            # Commenti e sezioni fuori dal blocco tickers preservati
            self.assertIn("# commento top-level da preservare", text)
            self.assertIn("module: scrapers.fgi_scraper", text)
            # Nuovo contenuto presente, vecchio commento interno sostituito
            self.assertIn("Booz Allen Hamilton", text)
            self.assertNotIn("vecchio commento interno", text)
            # Il backup contiene il file PRECEDENTE
            self.assertIn("vecchio commento interno",
                          backup.read_text(encoding="utf-8"))
            self.assertNotIn("Booz Allen Hamilton",
                             backup.read_text(encoding="utf-8"))
            # Il file salvato è YAML valido e passa la validazione pipeline
            config = yaml.safe_load(text)
            self.assertEqual(config["output"]["json_path"], "output/output.json")
            normalized = normalize_tickers(config["tickers"])
            self.assertEqual(normalized["defense"][0]["symbol"], "BAH")

    def test_save_appends_when_section_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, "output:\n  json_path: x.json\n")
            save_tickers(str(path), NEW_TICKERS)
            text = path.read_text(encoding="utf-8")
            config = yaml.safe_load(text)
            self.assertIn("defense", config["tickers"])

    def test_save_rejects_duplicate_symbol_without_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp)
            before = path.read_text(encoding="utf-8")
            backups_dir = Path(tmp) / "backups"
            invalid = {
                "a": [{"symbol": "AMAT", "name": "Uno"}],
                "b": [{"symbol": "amat", "name": "Duplicato (case-insensitive)"}],
            }
            with self.assertRaises(ValueError):
                save_tickers(str(path), invalid)
            self.assertEqual(path.read_text(encoding="utf-8"), before)
            self.assertFalse(backups_dir.exists())

    def test_save_rejects_empty_category_without_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp)
            before = path.read_text(encoding="utf-8")
            with self.assertRaises(ValueError):
                save_tickers(str(path), {"vuota": []})
            self.assertEqual(path.read_text(encoding="utf-8"), before)


class TestTickersPage(unittest.TestCase):
    def test_page_contains_data_and_controls(self):
        html = render_tickers_page(NEW_TICKERS)
        self.assertIn('id="tickers-data"', html)
        self.assertIn("BAH", html)
        self.assertIn('id="save-btn"', html)
        self.assertIn("/api/tickers/save", html)
        self.assertIn('data-action="remove-ticker"', html)
        self.assertIn('data-action="remove-category"', html)
        self.assertIn('data-action="add-ticker"', html)
        self.assertIn('id="add-category-btn"', html)

    def test_page_has_nav_menu(self):
        html = render_tickers_page(NEW_TICKERS)
        self.assertIn('class="page-nav"', html)
        self.assertIn('href="/report.html"', html)
        self.assertIn('href="/overrides.html"', html)
        self.assertIn('class="nav-link active">📋 Ticker</a>', html)

    def test_page_has_favicon(self):
        html = render_tickers_page(NEW_TICKERS)
        self.assertIn('rel="icon"', html)
        self.assertIn("data:image/svg+xml", html)

    def test_page_escapes_script_closing_sequence(self):
        html = render_tickers_page({"c": [{"symbol": "X", "name": "</script>"}]})
        self.assertNotIn("</script>\"}", html.replace("</script>", "", 1))


class TestExportTickers(unittest.TestCase):
    def test_export_returns_all_tickers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp)
            result = export_tickers(str(path))
            self.assertIn("exported_at", result)
            self.assertIn("tickers", result)
            self.assertIn("semiconductors", result["tickers"])
            self.assertEqual(result["tickers"]["semiconductors"][0]["symbol"], "AMAT")

    def test_export_empty_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, "output:\n  json_path: x.json\n")
            result = export_tickers(str(path))
            self.assertEqual(result["tickers"], {})


class TestImportTickers(unittest.TestCase):
    def test_import_new_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp)
            incoming = {"energy": [{"symbol": "VST", "name": "Vistra"}]}
            report = import_tickers(str(path), incoming)
            self.assertTrue(report["ok"])
            self.assertEqual(len(report["imported"]), 1)
            self.assertEqual(report["imported"][0]["symbol"], "VST")
            self.assertEqual(report["imported"][0]["category"], "energy")
            self.assertTrue(report["saved"])
            tickers = load_tickers(str(path))
            self.assertIn("energy", tickers)
            self.assertEqual(tickers["energy"][0]["symbol"], "VST")

    def test_import_existing_same_category_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp)
            incoming = {"semiconductors": [{"symbol": "AMAT", "name": "Applied Materials"}]}
            report = import_tickers(str(path), incoming)
            self.assertTrue(report["ok"])
            self.assertEqual(len(report["imported"]), 0)
            self.assertEqual(len(report["skipped"]), 1)
            self.assertEqual(report["skipped"][0]["symbol"], "AMAT")
            self.assertIn("already exists", report["skipped"][0]["reason"])
            self.assertFalse(report["saved"])

    def test_import_conflict_different_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp)
            incoming = {"defense": [{"symbol": "AMAT", "name": "Applied Materials"}]}
            report = import_tickers(str(path), incoming)
            self.assertTrue(report["ok"])
            self.assertEqual(len(report["imported"]), 0)
            self.assertEqual(len(report["conflicts"]), 1)
            self.assertEqual(report["conflicts"][0]["symbol"], "AMAT")
            self.assertEqual(report["conflicts"][0]["existing_category"], "semiconductors")
            self.assertEqual(report["conflicts"][0]["import_category"], "defense")
            self.assertFalse(report["saved"])

    def test_import_mixed_new_and_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp)
            incoming = {
                "semiconductors": [
                    {"symbol": "AMAT", "name": "Applied Materials"},
                    {"symbol": "NVDA", "name": "NVIDIA"},
                ],
                "defense": [
                    {"symbol": "AMAT", "name": "Applied Materials"},
                    {"symbol": "RTX", "name": "RTX"},
                ],
            }
            report = import_tickers(str(path), incoming)
            self.assertEqual(len(report["imported"]), 2)
            self.assertEqual(len(report["skipped"]), 1)
            self.assertEqual(len(report["conflicts"]), 1)
            self.assertTrue(report["saved"])

    def test_import_symbol_normalised_uppercase(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp)
            incoming = {"tech": [{"symbol": "aapl", "name": "Apple"}]}
            report = import_tickers(str(path), incoming)
            self.assertEqual(report["imported"][0]["symbol"], "AAPL")
            tickers = load_tickers(str(path))
            self.assertEqual(tickers["tech"][0]["symbol"], "AAPL")


if __name__ == "__main__":
    unittest.main()
