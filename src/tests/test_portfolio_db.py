"""Unit tests for portfolio transaction persistence (portfolio_db)."""

from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timezone

from portfolio_db import (
    TransactionError,
    add_transaction,
    delete_transaction,
    get_transaction,
    get_transactions,
    get_transactions_by_ticker,
    init_db,
    update_transaction,
)


def _conn() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with schema ready."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def _buy(
    conn: sqlite3.Connection,
    ticker: str = "NVDA",
    qty: float = 10,
    price: float = 125.50,
    commission: float = 1.0,
    date: str = "2026-08-27",
) -> dict:
    return add_transaction(
        conn,
        trade_date=date,
        ticker=ticker,
        action="BUY",
        quantity=qty,
        price_usd=price,
        commission_usd=commission,
    )


# ── Schema / init ────────────────────────────────────────────────────────────

class TestInit(unittest.TestCase):
    def test_init_creates_table(self):
        conn = _conn()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'"
        ).fetchone()
        self.assertIsNotNone(row)

    def test_init_idempotent(self):
        conn = _conn()
        init_db(conn)  # second call must not raise
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'"
        ).fetchone()
        self.assertIsNotNone(row)


# ── INSERT ───────────────────────────────────────────────────────────────────

class TestInsert(unittest.TestCase):
    def test_insert_buy(self):
        conn = _conn()
        tx = _buy(conn)
        self.assertEqual(tx["ticker"], "NVDA")
        self.assertEqual(tx["action"], "BUY")
        self.assertEqual(tx["quantity"], 10)
        self.assertEqual(tx["price_usd"], 125.50)
        self.assertEqual(tx["commission_usd"], 1.0)
        self.assertEqual(tx["trade_date"], "2026-08-27")
        self.assertIsNone(tx["note"])

    def test_insert_sell(self):
        conn = _conn()
        tx = add_transaction(
            conn,
            trade_date="2026-09-01",
            ticker="LMT",
            action="SELL",
            quantity=5,
            price_usd=450.0,
            commission_usd=2.0,
            note="Partial exit",
        )
        self.assertEqual(tx["action"], "SELL")
        self.assertEqual(tx["ticker"], "LMT")
        self.assertEqual(tx["note"], "Partial exit")

    def test_insert_with_note(self):
        conn = _conn()
        tx = add_transaction(
            conn,
            trade_date="2026-08-27",
            ticker="AMD",
            action="BUY",
            quantity=20,
            price_usd=150.0,
            commission_usd=1.5,
            note="First entry",
        )
        self.assertEqual(tx["note"], "First entry")

    def test_ticker_normalized_uppercase(self):
        conn = _conn()
        tx = add_transaction(
            conn,
            trade_date="2026-08-27",
            ticker="nvda",
            action="BUY",
            quantity=10,
            price_usd=100.0,
        )
        self.assertEqual(tx["ticker"], "NVDA")

    def test_ticker_stripped(self):
        conn = _conn()
        tx = add_transaction(
            conn,
            trade_date="2026-08-27",
            ticker="  nvda  ",
            action="BUY",
            quantity=10,
            price_usd=100.0,
        )
        self.assertEqual(tx["ticker"], "NVDA")


# ── Validation ───────────────────────────────────────────────────────────────

class TestValidation(unittest.TestCase):
    def test_invalid_action(self):
        conn = _conn()
        with self.assertRaises(TransactionError) as ctx:
            add_transaction(
                conn,
                trade_date="2026-08-27",
                ticker="NVDA",
                action="HOLD",
                quantity=10,
                price_usd=100.0,
            )
        self.assertIn("BUY or SELL", str(ctx.exception))

    def test_invalid_quantity_zero(self):
        conn = _conn()
        with self.assertRaises(TransactionError):
            add_transaction(
                conn,
                trade_date="2026-08-27",
                ticker="NVDA",
                action="BUY",
                quantity=0,
                price_usd=100.0,
            )

    def test_invalid_quantity_negative(self):
        conn = _conn()
        with self.assertRaises(TransactionError):
            add_transaction(
                conn,
                trade_date="2026-08-27",
                ticker="NVDA",
                action="BUY",
                quantity=-5,
                price_usd=100.0,
            )

    def test_invalid_price_negative(self):
        conn = _conn()
        with self.assertRaises(TransactionError):
            add_transaction(
                conn,
                trade_date="2026-08-27",
                ticker="NVDA",
                action="BUY",
                quantity=10,
                price_usd=-1.0,
            )

    def test_invalid_commission_negative(self):
        conn = _conn()
        with self.assertRaises(TransactionError):
            add_transaction(
                conn,
                trade_date="2026-08-27",
                ticker="NVDA",
                action="BUY",
                quantity=10,
                price_usd=100.0,
                commission_usd=-5.0,
            )

    def test_missing_ticker(self):
        conn = _conn()
        with self.assertRaises(TransactionError):
            add_transaction(
                conn,
                trade_date="2026-08-27",
                ticker="",
                action="BUY",
                quantity=10,
                price_usd=100.0,
            )

    def test_missing_trade_date(self):
        conn = _conn()
        with self.assertRaises(TransactionError):
            add_transaction(
                conn,
                trade_date="",
                ticker="NVDA",
                action="BUY",
                quantity=10,
                price_usd=100.0,
            )


# ── READ ─────────────────────────────────────────────────────────────────────

class TestRead(unittest.TestCase):
    def test_get_transaction(self):
        conn = _conn()
        tx = _buy(conn)
        fetched = get_transaction(conn, tx["id"])
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["id"], tx["id"])

    def test_get_nonexistent(self):
        conn = _conn()
        self.assertIsNone(get_transaction(conn, 9999))

    def test_get_all(self):
        conn = _conn()
        _buy(conn, ticker="NVDA")
        _buy(conn, ticker="AMD")
        all_tx = get_transactions(conn)
        self.assertEqual(len(all_tx), 2)

    def test_get_by_ticker(self):
        conn = _conn()
        _buy(conn, ticker="NVDA")
        _buy(conn, ticker="AMD")
        _buy(conn, ticker="NVDA")
        nvda_tx = get_transactions_by_ticker(conn, "NVDA")
        self.assertEqual(len(nvda_tx), 2)
        self.assertTrue(all(t["ticker"] == "NVDA" for t in nvda_tx))

    def test_get_by_ticker_case_insensitive(self):
        conn = _conn()
        _buy(conn, ticker="NVDA")
        result = get_transactions_by_ticker(conn, "nvda")
        self.assertEqual(len(result), 1)

    def test_ordering_by_date(self):
        conn = _conn()
        _buy(conn, date="2026-09-01")
        _buy(conn, date="2026-08-01")
        _buy(conn, date="2026-08-15")
        dates = [t["trade_date"] for t in get_transactions(conn)]
        self.assertEqual(dates, ["2026-08-01", "2026-08-15", "2026-09-01"])


# ── UPDATE ───────────────────────────────────────────────────────────────────

class TestUpdate(unittest.TestCase):
    def test_update_fields(self):
        conn = _conn()
        tx = _buy(conn)
        updated = update_transaction(
            conn,
            tx["id"],
            quantity=20,
            price_usd=130.0,
            note="Updated",
        )
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated["quantity"], 20)
        self.assertEqual(updated["price_usd"], 130.0)
        self.assertEqual(updated["note"], "Updated")
        # unchanged fields preserved
        self.assertEqual(updated["ticker"], "NVDA")
        self.assertEqual(updated["action"], "BUY")

    def test_update_nonexistent(self):
        conn = _conn()
        result = update_transaction(conn, 9999, quantity=10)
        self.assertIsNone(result)

    def test_update_validates(self):
        conn = _conn()
        tx = _buy(conn)
        with self.assertRaises(TransactionError):
            update_transaction(conn, tx["id"], quantity=-5)

    def test_update_ticker_uppercase(self):
        conn = _conn()
        tx = _buy(conn)
        updated = update_transaction(conn, tx["id"], ticker="amd")
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated["ticker"], "AMD")


# ── DELETE ───────────────────────────────────────────────────────────────────

class TestDelete(unittest.TestCase):
    def test_delete_existing(self):
        conn = _conn()
        tx = _buy(conn)
        self.assertTrue(delete_transaction(conn, tx["id"]))
        self.assertIsNone(get_transaction(conn, tx["id"]))

    def test_delete_nonexistent(self):
        conn = _conn()
        self.assertFalse(delete_transaction(conn, 9999))

    def test_delete_does_not_affect_others(self):
        conn = _conn()
        tx1 = _buy(conn, ticker="NVDA")
        tx2 = _buy(conn, ticker="AMD")
        delete_transaction(conn, tx1["id"])
        remaining = get_transactions(conn)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["ticker"], "AMD")


# ── Timestamps & trigger ─────────────────────────────────────────────────────

class TestTimestamps(unittest.TestCase):
    def test_created_at_and_updated_at_on_insert(self):
        conn = _conn()
        tx = _buy(conn)
        self.assertIsNotNone(tx["created_at"])
        self.assertIsNotNone(tx["updated_at"])
        self.assertEqual(tx["created_at"], tx["updated_at"])

    def test_updated_at_changes_on_update(self):
        conn = _conn()
        tx = _buy(conn)
        old_updated = tx["updated_at"]
        import time
        time.sleep(0.05)
        updated = update_transaction(conn, tx["id"], quantity=20)
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertNotEqual(updated["updated_at"], old_updated)

    def test_created_at_does_not_change_on_update(self):
        conn = _conn()
        tx = _buy(conn)
        old_created = tx["created_at"]
        import time
        time.sleep(0.05)
        updated = update_transaction(conn, tx["id"], quantity=20)
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated["created_at"], old_created)


if __name__ == "__main__":
    unittest.main()
