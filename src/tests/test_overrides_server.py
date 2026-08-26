"""Unit tests for the manual overrides mini-server (API + rebuild)."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from overrides_page import render_overrides_page
from overrides_server import OverridesHandler, SUPPORTED_KEYS, rebuild_report


class TestOverridesPageNav(unittest.TestCase):
    def test_overrides_page_has_nav_menu(self):
        html = render_overrides_page({})
        self.assertIn('class="page-nav"', html)
        self.assertIn('href="/report.html"', html)
        self.assertIn('href="/tickers.html"', html)
        self.assertIn('class="nav-link active">✍️ Immissione manuale</a>', html)


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
    def test_supported_keys_whitelist(self):
        self.assertEqual(
            SUPPORTED_KEYS,
            frozenset({"aaii", "fgi", "naaim", "vix_term_structure", "pct_sma"}),
        )

    def test_root_redirects_to_dashboard(self):
        # La landing page di default è la dashboard: / → 302 /report.html
        server = ThreadingHTTPServer(("127.0.0.1", 0), OverridesHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]

            class _NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
                    return None

            opener = urllib.request.build_opener(_NoRedirect())
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                opener.open(f"http://127.0.0.1:{port}/", timeout=5)
            self.assertEqual(ctx.exception.status, 302)
            self.assertEqual(ctx.exception.headers["Location"], "/report.html")
        finally:
            server.shutdown()
            server.server_close()
