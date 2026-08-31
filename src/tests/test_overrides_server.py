"""Unit tests for the manual overrides mini-server (API + rebuild)."""

from __future__ import annotations

import base64
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
from overrides_server import (
    OverridesHandler,
    SUPPORTED_KEYS,
    is_authorized,
    load_credentials,
    parse_number,
    rebuild_report,
)

# Credenziali fittizie per i test (mai usate in produzione).
_TEST_CREDS = ("testuser", "testpass")


class TestParseNumber(unittest.TestCase):
    def test_accepts_dot_and_comma_as_decimal_separator(self):
        self.assertEqual(parse_number("12.5"), 12.5)
        self.assertEqual(parse_number("12,5"), 12.5)
        self.assertEqual(parse_number(" 12,5 "), 12.5)
        self.assertEqual(parse_number(24), 24.0)
        self.assertEqual(parse_number("79,70"), 79.7)

    def test_rejects_non_numeric(self):
        with self.assertRaises(ValueError):
            parse_number("abc")
        with self.assertRaises(ValueError):
            parse_number("")


def _auth_header(user: str = "", password: str = "") -> str:
    user = user or _TEST_CREDS[0]
    password = password or _TEST_CREDS[1]
    raw = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode()
    return f"Basic {raw}"


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


class TestBasicAuth(unittest.TestCase):
    def test_is_authorized_valid_credentials(self):
        self.assertTrue(is_authorized(_auth_header(), credentials=_TEST_CREDS))

    def test_is_authorized_rejects_missing_header(self):
        self.assertFalse(is_authorized(None, credentials=_TEST_CREDS))
        self.assertFalse(is_authorized("", credentials=_TEST_CREDS))

    def test_is_authorized_rejects_wrong_password(self):
        self.assertFalse(is_authorized(_auth_header(password="sbagliata"),
                                       credentials=_TEST_CREDS))

    def test_is_authorized_rejects_wrong_user(self):
        self.assertFalse(is_authorized(_auth_header(user="altro"),
                                       credentials=_TEST_CREDS))

    def test_is_authorized_rejects_malformed_header(self):
        self.assertFalse(is_authorized("Basic !!!non-base64!!!", credentials=_TEST_CREDS))
        self.assertFalse(is_authorized("Bearer abc123", credentials=_TEST_CREDS))

    def test_load_credentials_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth_file = Path(tmp) / ".server-auth"
            auth_file.write_text("pippo:pluto €\n", encoding="utf-8")
            self.assertEqual(load_credentials(auth_file), ("pippo", "pluto €"))

    def test_load_credentials_raises_when_file_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth_file = Path(tmp) / ".server-auth"
            auth_file.write_text("senza-separatore\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                load_credentials(auth_file)

    def test_load_credentials_raises_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                load_credentials(Path(tmp) / "inesistente")


class TestOverridesHandler(unittest.TestCase):
    def setUp(self):
        self._cred_patcher = mock.patch(
            "overrides_server.load_credentials", return_value=_TEST_CREDS,
        )
        self._cred_patcher.start()

    def tearDown(self):
        self._cred_patcher.stop()

    def test_supported_keys_whitelist(self):
        self.assertEqual(
            SUPPORTED_KEYS,
            frozenset({"aaii", "fgi", "naaim", "vix_term_structure", "pct_sma"}),
        )

    def _start_server(self) -> tuple[ThreadingHTTPServer, threading.Thread, int]:
        server = ThreadingHTTPServer(("127.0.0.1", 0), OverridesHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread, server.server_address[1]

    @staticmethod
    def _open_no_redirect(url: str, headers: dict[str, str] | None = None):
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
                return None

        opener = urllib.request.build_opener(_NoRedirect())
        request = urllib.request.Request(url, headers=headers or {})
        return opener.open(request, timeout=5)

    def test_unauthenticated_request_gets_401_with_challenge(self):
        server, thread, port = self._start_server()
        try:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self._open_no_redirect(f"http://127.0.0.1:{port}/report.html")
            self.assertEqual(ctx.exception.status, 401)
            self.assertIn("Basic", ctx.exception.headers["WWW-Authenticate"])
        finally:
            server.shutdown()
            server.server_close()

    def test_root_redirects_to_dashboard_when_authenticated(self):
        # La landing page di default è la dashboard: / → 302 /report.html
        server, thread, port = self._start_server()
        try:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self._open_no_redirect(
                    f"http://127.0.0.1:{port}/",
                    headers={"Authorization": _auth_header()},
                )
            self.assertEqual(ctx.exception.status, 302)
            self.assertEqual(ctx.exception.headers["Location"], "/report.html")
        finally:
            server.shutdown()
            server.server_close()

    def test_api_data_accessible_when_authenticated(self):
        server, thread, port = self._start_server()
        try:
            response = urllib.request.urlopen(
                urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/data",
                    headers={"Authorization": _auth_header()},
                ),
                timeout=5,
            )
            payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
        finally:
            server.shutdown()
            server.server_close()
