"""Unit tests for the orchestrator and its modules."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest

from audit import init_db, record_execution
from config_loader import load_config, validate_config
from consolidator import consolidate
from orchestrator import run
from registry import get_scraper


def _register_mock_scraper() -> str:
    """Register a deterministic fake scraper module and return its name."""
    module = types.ModuleType("tests.mock_scraper")

    def run(config):
        return {"score": 42, "zone": "fear", "status": "fresh"}

    module.run = run
    sys.modules["tests.mock_scraper"] = module
    return "tests.mock_scraper"


class TestConfigLoader(unittest.TestCase):
    def test_loads_valid_config(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write(
                "scrapers:\n"
                "  fgi:\n"
                "    module: scrapers.fgi_scraper\n"
                "    output_key: fgi\n"
                "    schedule: daily\n"
            )
            path = fh.name
        config = load_config(path)
        self.assertIn("fgi", config["scrapers"])

    def test_rejects_missing_scrapers(self):
        with self.assertRaises(ValueError):
            validate_config({})

    def test_rejects_missing_scraper_field(self):
        with self.assertRaises(ValueError):
            validate_config({"scrapers": {"fgi": {"module": "x"}}})

    def test_rejects_invalid_schedule(self):
        with self.assertRaises(ValueError):
            validate_config(
                {
                    "scrapers": {
                        "fgi": {
                            "module": "x",
                            "output_key": "fgi",
                            "schedule": "hourly",
                        }
                    }
                }
            )

    def test_rejects_invalid_scheduler_interval(self):
        with self.assertRaises(ValueError):
            validate_config(
                {
                    "scrapers": {
                        "fgi": {
                            "module": "x",
                            "output_key": "fgi",
                            "schedule": "daily",
                        }
                    },
                    "scheduler": {"interval": "monthly"},
                }
            )

    def test_rejects_invalid_scheduler_run_at(self):
        with self.assertRaises(ValueError):
            validate_config(
                {
                    "scrapers": {
                        "fgi": {
                            "module": "x",
                            "output_key": "fgi",
                            "schedule": "daily",
                        }
                    },
                    "scheduler": {"run_at": "25:00"},
                }
            )

    def test_rejects_invalid_scheduler_weekday(self):
        with self.assertRaises(ValueError):
            validate_config(
                {
                    "scrapers": {
                        "fgi": {
                            "module": "x",
                            "output_key": "fgi",
                            "schedule": "daily",
                        }
                    },
                    "scheduler": {"weekday": 7},
                }
            )

    def test_accepts_valid_scheduler(self):
        config = validate_config(
            {
                "scrapers": {
                    "fgi": {
                        "module": "x",
                        "output_key": "fgi",
                        "schedule": "daily",
                    }
                },
                "scheduler": {"interval": "weekly", "run_at": "08:30", "weekday": 2},
            }
        )
        self.assertEqual(config["scheduler"]["interval"], "weekly")


class TestRegistry(unittest.TestCase):
    def test_returns_run_callable(self):
        run_fn = get_scraper("scrapers.fgi_scraper")
        self.assertTrue(callable(run_fn))

    def test_unknown_module_raises(self):
        with self.assertRaises(ValueError):
            get_scraper("no.such.module")


class TestAudit(unittest.TestCase):
    def test_init_and_record(self):
        conn = sqlite3.connect(":memory:")
        init_db(conn)
        record_execution(conn, "fgi", "2026-08-07T08:00:00", "success")
        row = conn.execute("SELECT scraper, status FROM executions").fetchone()
        self.assertEqual(row, ("fgi", "success"))
        conn.close()


class TestConsolidator(unittest.TestCase):
    def test_consolidates_results(self):
        results = {
            "fgi": {"score": 42, "status": "fresh"},
            "pcr": {"value": 0.78, "status": "stale"},
        }
        output = consolidate(results, generated_at="2026-08-07T08:00:00")
        self.assertEqual(output["generated_at"], "2026-08-07T08:00:00")
        self.assertEqual(output["fgi"]["score"], 42)
        summary = output["stale_summary"]
        self.assertEqual(summary["total_sources"], 2)
        self.assertEqual(summary["fresh"], 1)
        self.assertEqual(summary["stale"], 1)

    def test_error_source_counts_as_stale_and_low_reliability(self):
        results = {
            "fgi": {"score": 42, "status": "fresh"},
            "aaii": {"status": "error", "error": "AAII fetch failed"},
        }
        output = consolidate(results)
        summary = output["stale_summary"]
        self.assertEqual(summary["total_sources"], 2)
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["stale"], 1)
        self.assertEqual(summary["signal_reliability"], "low")
        self.assertTrue(any("aaii" in d for d in summary["stale_details"]))

    def test_all_down_is_low_reliability_not_high(self):
        # Fail-closed: un sistema con 0 sorgenti non deve mai dire "high".
        output = consolidate({})
        summary = output["stale_summary"]
        self.assertEqual(summary["total_sources"], 0)
        self.assertEqual(summary["signal_reliability"], "low")

    def test_stale_source_keeps_medium_reliability(self):
        results = {
            "fgi": {"score": 42, "status": "fresh"},
            "pcr": {"value": 0.78, "status": "stale"},
        }
        summary = consolidate(results)["stale_summary"]
        self.assertEqual(summary["signal_reliability"], "medium")

    def test_all_fresh_is_high_reliability(self):
        results = {
            "fgi": {"score": 42, "status": "fresh"},
            "vix": {"vix_close": 15.0, "status": "fresh"},
        }
        summary = consolidate(results)["stale_summary"]
        self.assertEqual(summary["signal_reliability"], "high")


class TestOrchestrator(unittest.TestCase):
    def test_run_flow_with_mocked_scraper(self):
        module = _register_mock_scraper()
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/config.yaml"
            output_path = f"{tmp}/output.json"
            db_path = f"{tmp}/audit.db"
            with open(config_path, "w", encoding="utf-8") as fh:
                fh.write(
                    "scrapers:\n"
                    "  fgi:\n"
                    f"    module: {module}\n"
                    "    output_key: fgi\n"
                    "    schedule: daily\n"
                )
            output = run(config_path, output_path, db_path)
            self.assertIn("generated_at", output)
            self.assertIn("stale_summary", output)
            self.assertEqual(output["fgi"]["score"], 42)
            with open(output_path, encoding="utf-8") as fh:
                saved = json.load(fh)
            self.assertEqual(saved["generated_at"], output["generated_at"])
            conn = sqlite3.connect(db_path)
            count = conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
            self.assertEqual(count, 1)
            conn.close()

    def test_run_injects_tickers_to_scraper_config(self):
        received = {}

        module = types.ModuleType("tests.mock_ticker_scraper")

        def mock_run(config):
            received["tickers"] = config.get("tickers")
            return {"status": "fresh"}

        module.run = mock_run
        sys.modules["tests.mock_ticker_scraper"] = module
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/config.yaml"
            output_path = f"{tmp}/output.json"
            db_path = f"{tmp}/audit.db"
            with open(config_path, "w", encoding="utf-8") as fh:
                fh.write(
                    "scrapers:\n"
                    "  mock:\n"
                    "    module: tests.mock_ticker_scraper\n"
                    "    output_key: mock\n"
                    "    schedule: daily\n"
                    "tickers:\n"
                    "  semiconductors:\n"
                    "    - symbol: AMAT\n"
                    "      name: Applied Materials\n"
                )
            run(config_path, output_path, db_path)
        self.assertEqual(
            received["tickers"]["semiconductors"][0]["symbol"], "AMAT"
        )

    def test_run_records_failed_scraper_as_error_in_output(self):
        # Fail-closed: un modulo che fallisce NON sparisce dall'output — deve
        # comparire con status "error" e il summary deve dirlo.
        module = types.ModuleType("tests.mock_failing_scraper")

        def fail_run(config):
            raise RuntimeError("boom")

        module.run = fail_run
        sys.modules["tests.mock_failing_scraper"] = module
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/config.yaml"
            output_path = f"{tmp}/output.json"
            db_path = f"{tmp}/audit.db"
            with open(config_path, "w", encoding="utf-8") as fh:
                fh.write(
                    "scrapers:\n"
                    "  failing:\n"
                    f"    module: tests.mock_failing_scraper\n"
                    "    output_key: failing\n"
                    "    schedule: daily\n"
                )
            output = run(config_path, output_path, db_path)
        self.assertEqual(output["failing"]["status"], "error")
        self.assertIn("boom", output["failing"]["error"])
        summary = output["stale_summary"]
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["signal_reliability"], "low")

    def test_run_injects_strategy_indicators_matrix(self):
        module = _register_mock_scraper()
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/config.yaml"
            output_path = f"{tmp}/output.json"
            db_path = f"{tmp}/audit.db"
            with open(config_path, "w", encoding="utf-8") as fh:
                fh.write(
                    "scrapers:\n"
                    "  fgi:\n"
                    f"    module: {module}\n"
                    "    output_key: fgi\n"
                    "    schedule: daily\n"
                    "strategy:\n"
                    "  proxy_accepted: []\n"
                )
            output = run(config_path, output_path, db_path)
        self.assertIn("strategy_indicators", output)
        matrix = output["strategy_indicators"]
        # Default fail-closed: i proxy NON sono usabili nello score
        self.assertFalse(matrix["vix_spot"]["usable_in_strategy_score"])
        self.assertFalse(matrix["pct_sma"]["usable_in_strategy_score"])
        # Coverage (STATICO, dalle specifiche): true per TUTTI gli indicatori
        # della strategia, anche missing; false per vix_spot (non strategico)
        self.assertFalse(matrix["vix_spot"]["coverage"])
        self.assertTrue(matrix["pct_sma"]["coverage"])
        self.assertTrue(matrix["nyse_nh_nl"]["coverage"])
        self.assertTrue(matrix["vix_term_structure"]["coverage"])
        # Availability: solo i moduli che nel run hanno prodotto "fresh".
        # Il mock fgi è fresh → available; aaii non ha modulo → unavailable.
        self.assertTrue(matrix["fgi"]["availability"])
        self.assertFalse(matrix["aaii"]["availability"])
        # Usabile: implemented E available (fgi sì); implemented ma non
        # disponibile (aaii no, nessun modulo nel run) → NON usabile.
        self.assertTrue(matrix["fgi"]["usable_in_strategy_score"])
        self.assertFalse(matrix["aaii"]["usable_in_strategy_score"])
        # I gap dichiarati restano missing (implementation_status) e mai usabili
        self.assertEqual(matrix["nyse_nh_nl"]["implementation_status"], "missing")
        self.assertEqual(matrix["vix_term_structure"]["implementation_status"], "missing")

    def test_run_applies_manual_override_when_scraper_fails(self):
        # Fail-closed + manual override: un modulo che fallisce viene
        # sostituito da un override manuale valido e fresco (source=manual).
        module = types.ModuleType("tests.mock_failing_override_scraper")

        def fail_run(config):
            raise RuntimeError("source down")

        module.run = fail_run
        sys.modules["tests.mock_failing_override_scraper"] = module
        from datetime import datetime, timedelta, timezone

        fresh_ts = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/config.yaml"
            output_path = f"{tmp}/output.json"
            db_path = f"{tmp}/audit.db"
            overrides_path = f"{tmp}/manual_overrides.yaml"
            with open(overrides_path, "w", encoding="utf-8") as fh:
                fh.write(
                    "fgi:\n"
                    "  score: 62.66\n"
                    "  zone: \"greed\"\n"
                    "  source: manual\n"
                    f'  fetched_at: "{fresh_ts}"\n'
                    "  stale_after_hours: 24\n"
                    "  entered_by: \"user\"\n"
                    '  note: "Inserito manualmente"\n'
                )
            with open(config_path, "w", encoding="utf-8") as fh:
                fh.write(
                    "scrapers:\n"
                    "  fgi:\n"
                    f"    module: tests.mock_failing_override_scraper\n"
                    "    output_key: fgi\n"
                    "    schedule: daily\n"
                    "strategy:\n"
                    "  proxy_accepted: []\n"
                    "  manual_overrides: manual_overrides.yaml\n"
                )
            output = run(config_path, output_path, db_path)
        self.assertEqual(output["fgi"]["source"], "manual")
        self.assertEqual(output["fgi"]["origin"], "manual")
        self.assertEqual(output["fgi"]["score"], 62.66)
        self.assertEqual(output["fgi"]["status"], "fresh")
        self.assertEqual(output["fgi"]["entered_by"], "user")
        matrix = output["strategy_indicators"]
        self.assertEqual(matrix["fgi"]["source"], "manual")
        self.assertTrue(matrix["fgi"]["availability"])

    def test_run_resolves_cache_path_relative_to_project_root(self):
        received = {}

        module = types.ModuleType("tests.mock_cache_scraper")

        def mock_run(config):
            received["cache_path"] = config.get("cache_path")
            return {"status": "fresh"}

        module.run = mock_run
        sys.modules["tests.mock_cache_scraper"] = module
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/config.yaml"
            output_path = f"{tmp}/output.json"
            db_path = f"{tmp}/audit.db"
            with open(config_path, "w", encoding="utf-8") as fh:
                fh.write(
                    "scrapers:\n"
                    "  mock:\n"
                    "    module: tests.mock_cache_scraper\n"
                    "    output_key: mock\n"
                    "    schedule: daily\n"
                    "    config:\n"
                    "      cache_path: output/ohlcv_cache.json\n"
                )
            run(config_path, output_path, db_path)
        self.assertEqual(
            received["cache_path"],
            os.path.join(tmp, "output", "ohlcv_cache.json"),
        )


if __name__ == "__main__":
    unittest.main()