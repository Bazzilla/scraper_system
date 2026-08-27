"""Unit tests for portfolio API endpoints (overrides_server)."""

from __future__ import annotations

import base64
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from overrides_server import OverridesHandler, PORTFOLIO_DB
from portfolio_db import init_db


# ── Helpers ──────────────────────────────────────────────────────────────────

DEFAULT_CREDS = ("admin", "so€uri€€€")


def _auth_header(user: str = "", password: str = "") -> str:
    user = user or DEFAULT_CREDS[0]
    password = password or DEFAULT_CREDS[1]
    raw = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode()
    return f"Basic {raw}"


def _start_server() -> tuple[ThreadingHTTPServer, threading.Thread, int, Path]:
    """Start a server with an in-memory portfolio DB."""
    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "portfolio.db"

    # Patch _portfolio_conn to return in-memory connection.
    _orig = OverridesHandler.__dict__

    def _mock_conn():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_db(conn)
        return conn

    server = ThreadingHTTPServer(("127.0.0.1", 0), OverridesHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    # Apply the patch on the handler class.
    OverridesHandler._orig_portfolio_conn = None  # type: ignore[attr-defined]
    import overrides_server as _mod
    _mod._portfolio_conn = _mock_conn  # type: ignore[attr-defined]

    return server, thread, port, Path(tmp)


def _stop_server(server: ThreadingHTTPServer, tmp: Path) -> None:
    server.shutdown()
    server.server_close()
    # Clean up patch.
    import overrides_server as _mod
    if hasattr(_mod, "_orig_portfolio_conn"):
        del _mod._orig_portfolio_conn  # type: ignore[attr-defined]


def _req(
    port: int,
    method: str,
    path: str,
    body: dict | None = None,
) -> tuple[int, dict]:
    """Send an HTTP request and return (status, parsed_json)."""
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", _auth_header())
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.status, json.loads(exc.read().decode("utf-8"))


# ── Tests ────────────────────────────────────────────────────────────────────

class TestTransactionsAPI(unittest.TestCase):
    def setUp(self):
        self.server, self.thread, self.port, self.tmp = _start_server()

    def tearDown(self):
        _stop_server(self.server, self.tmp)

    def test_get_empty_transactions(self):
        status, data = _req(self.port, "GET", "/api/transactions")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["transactions"], [])

    def test_post_and_get_transaction(self):
        payload = {
            "trade_date": "2026-08-27",
            "ticker": "NVDA",
            "action": "BUY",
            "quantity": 10,
            "price_usd": 125.50,
            "commission_usd": 1.0,
            "note": "Test",
        }
        status, data = _req(self.port, "POST", "/api/transactions", payload)
        self.assertEqual(status, 201)
        self.assertTrue(data["ok"])
        tx = data["transaction"]
        self.assertEqual(tx["ticker"], "NVDA")
        self.assertEqual(tx["action"], "BUY")
        self.assertEqual(tx["quantity"], 10)

        # GET by id
        tx_id = tx["id"]
        status, data = _req(self.port, "GET", f"/api/transactions/{tx_id}")
        self.assertEqual(status, 200)
        self.assertEqual(data["transaction"]["ticker"], "NVDA")

    def test_post_invalid_action(self):
        payload = {
            "trade_date": "2026-08-27",
            "ticker": "NVDA",
            "action": "HOLD",
            "quantity": 10,
            "price_usd": 100.0,
        }
        status, data = _req(self.port, "POST", "/api/transactions", payload)
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])

    def test_post_invalid_quantity(self):
        payload = {
            "trade_date": "2026-08-27",
            "ticker": "NVDA",
            "action": "BUY",
            "quantity": 0,
            "price_usd": 100.0,
        }
        status, data = _req(self.port, "POST", "/api/transactions", payload)
        self.assertEqual(status, 400)

    def test_put_transaction(self):
        # Create
        payload = {
            "trade_date": "2026-08-27",
            "ticker": "NVDA",
            "action": "BUY",
            "quantity": 10,
            "price_usd": 100.0,
        }
        _, data = _req(self.port, "POST", "/api/transactions", payload)
        tx_id = data["transaction"]["id"]

        # Update
        status, data = _req(
            self.port, "PUT", f"/api/transactions/{tx_id}",
            {"quantity": 20, "note": "Updated"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["transaction"]["quantity"], 20)
        self.assertEqual(data["transaction"]["note"], "Updated")

    def test_delete_transaction(self):
        # Create
        payload = {
            "trade_date": "2026-08-27",
            "ticker": "NVDA",
            "action": "BUY",
            "quantity": 10,
            "price_usd": 100.0,
        }
        _, data = _req(self.port, "POST", "/api/transactions", payload)
        tx_id = data["transaction"]["id"]

        # Delete
        status, data = _req(self.port, "DELETE", f"/api/transactions/{tx_id}")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])

        # Verify gone
        status, _ = _req(self.port, "GET", f"/api/transactions/{tx_id}")
        self.assertEqual(status, 404)

    def test_get_nonexistent_transaction(self):
        status, _ = _req(self.port, "GET", "/api/transactions/9999")
        self.assertEqual(status, 404)

    def test_delete_nonexistent_transaction(self):
        status, data = _req(self.port, "DELETE", "/api/transactions/9999")
        self.assertEqual(status, 404)


class TestPositionsAPI(unittest.TestCase):
    def setUp(self):
        self.server, self.thread, self.port, self.tmp = _start_server()

    def tearDown(self):
        _stop_server(self.server, self.tmp)

    def _seed_transactions(self):
        """Insert test transactions via the API."""
        txs = [
            {"trade_date": "2026-08-01", "ticker": "NVDA", "action": "BUY",
             "quantity": 10, "price_usd": 100.0, "commission_usd": 0.0},
            {"trade_date": "2026-08-05", "ticker": "LMT", "action": "BUY",
             "quantity": 5, "price_usd": 400.0, "commission_usd": 0.0},
        ]
        for tx in txs:
            _req(self.port, "POST", "/api/transactions", tx)

    def test_get_positions_empty(self):
        status, data = _req(self.port, "GET", "/api/positions")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["positions"], [])

    def test_get_positions_after_buys(self):
        self._seed_transactions()
        status, data = _req(self.port, "GET", "/api/positions")
        self.assertEqual(status, 200)
        tickers = {p["ticker"] for p in data["positions"]}
        self.assertIn("NVDA", tickers)
        self.assertIn("LMT", tickers)

    def test_get_position_by_ticker(self):
        self._seed_transactions()
        status, data = _req(self.port, "GET", "/api/positions/NVDA")
        self.assertEqual(status, 200)
        self.assertEqual(data["position"]["ticker"], "NVDA")
        self.assertEqual(data["position"]["quantity"], 10)

    def test_get_position_nonexistent_ticker(self):
        status, _ = _req(self.port, "GET", "/api/positions/ZZZZ")
        self.assertEqual(status, 404)

    def test_positions_reflect_sell(self):
        self._seed_transactions()
        # Sell half NVDA
        _req(self.port, "POST", "/api/transactions", {
            "trade_date": "2026-08-10", "ticker": "NVDA", "action": "SELL",
            "quantity": 5, "price_usd": 120.0, "commission_usd": 0.0,
        })
        status, data = _req(self.port, "GET", "/api/positions/NVDA")
        self.assertEqual(status, 200)
        self.assertEqual(data["position"]["quantity"], 5)
        self.assertAlmostEqual(data["position"]["realized_pnl_usd"], 100.0)


class TestPortfolioEvaluate(unittest.TestCase):
    def setUp(self):
        self.server, self.thread, self.port, self.tmp = _start_server()

    def tearDown(self):
        _stop_server(self.server, self.tmp)

    def test_evaluate_no_positions(self):
        status, data = _req(self.port, "GET", "/api/portfolio/evaluate")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIsInstance(data["evaluations"], list)

    def test_evaluate_with_positions(self):
        _seed_transactions_static(self.port)
        status, data = _req(self.port, "GET", "/api/portfolio/evaluate")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIsInstance(data["evaluations"], list)

    def test_evaluate_without_output_json(self):
        """Evaluate works even without output.json (returns empty list)."""
        status, data = _req(self.port, "GET", "/api/portfolio/evaluate")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])


def _seed_transactions_static(port: int) -> None:
    """Seed transactions for evaluate tests."""
    _req(port, "POST", "/api/transactions", {
        "trade_date": "2026-08-01", "ticker": "NVDA", "action": "BUY",
        "quantity": 10, "price_usd": 100.0, "commission_usd": 1.0,
    })


class TestAuthRequired(unittest.TestCase):
    def setUp(self):
        self.server, self.thread, self.port, self.tmp = _start_server()

    def tearDown(self):
        _stop_server(self.server, self.tmp)

    def test_unauthenticated_get_transactions(self):
        url = f"http://127.0.0.1:{self.port}/api/transactions"
        req = urllib.request.Request(url)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.status, 401)

    def test_unauthenticated_post_transaction(self):
        url = f"http://127.0.0.1:{self.port}/api/transactions"
        data = json.dumps({"trade_date": "2026-08-27", "ticker": "NVDA",
                           "action": "BUY", "quantity": 10,
                           "price_usd": 100.0}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.status, 401)


if __name__ == "__main__":
    unittest.main()
