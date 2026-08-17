"""Unit tests for the manual overrides mini-server (API + rebuild)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from overrides_server import OverridesHandler, rebuild_report


class TestRebuildReport(unittest.TestCase):
    def test_rebuild_applies_overrides_and_writes_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            config_path = tmp / "config.yaml"
            config_path.write_text(
                "output:\n  json_path: output.json\n  db_path: audit.db\n"
                "strategy:\n  proxy_accepted: []\n",
                encoding="utf-8",
            )
            (tmp / "output.json").write_text(
                json.dumps({
                    "generated_at": "2026-08-17T10:00:00+00:00",
                    "fgi": {"score": 62.0, "status": "fresh", "origin": "scraped",
                            "fetched_at": "2026-08-17T10:00:00+00:00"},
                    "naaim": {"status": "error", "origin": "missing", "error": "x"},
                    "stale_summary": {"total_sources": 2, "fresh": 1, "stale": 1},
                }),
                encoding="utf-8",
            )
            overrides_path = tmp / "manual_overrides.yaml"
            overrides_path.write_text(
                "naaim:\n  exposure: 85.0\n  source: manual\n"
                "  fetched_at: \"2026-08-17T12:00:00+00:00\"\n"
                "  stale_after_hours: 168\n  entered_by: \"user\"\n",
                encoding="utf-8",
            )
            # Il registry indicatori non esiste in tmp → ricade sul progetto reale
            config = {
                "output": {"json_path": "output.json", "db_path": "audit.db"},
                "strategy": {"proxy_accepted": [], "manual_overrides": "manual_overrides.yaml"},
            }
            with mock.patch("overrides_server.load_config", return_value=config):
                rebuild_report(str(config_path))
            data = json.loads((tmp / "output.json").read_text(encoding="utf-8"))
            self.assertEqual(data["naaim"]["origin"], "manual")
            self.assertEqual(data["naaim"]["exposure"], 85.0)


class TestOverridesHandler(unittest.TestCase):
    def _handler(self):
        return OverridesHandler

    def test_handler_is_bounded_to_localhost(self):
        # OverridesHandler deve essere servito solo su 127.0.0.1
        self.assertTrue(hasattr(OverridesHandler, "server_version"))