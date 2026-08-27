"""SQLite persistence for portfolio transactions.

Stores BUY / SELL transactions.  Positions are *derived* from the
transaction history (see portfolio.py for the calculation layer).

DB is separate from scraper_audit.db — different concerns, different data.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


# ── Schema ───────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('BUY', 'SELL')),
    quantity REAL NOT NULL CHECK(quantity > 0),
    price_usd REAL NOT NULL CHECK(price_usd >= 0),
    commission_usd REAL NOT NULL DEFAULT 0 CHECK(commission_usd >= 0),
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS trg_transactions_updated_at
AFTER UPDATE ON transactions
FOR EACH ROW
BEGIN
    UPDATE transactions
    SET updated_at = datetime('now')
    WHERE id = NEW.id;
END;
"""


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ── Init ─────────────────────────────────────────────────────────────────────

def init_db(conn: sqlite3.Connection) -> None:
    """Create the transactions table + trigger if they do not exist."""
    conn.executescript(_SCHEMA)
    conn.commit()


# ── Validation ───────────────────────────────────────────────────────────────

class TransactionError(Exception):
    """Raised when transaction input fails validation."""


def _validate_transaction(
    ticker: str,
    action: str,
    quantity: float,
    price_usd: float,
    commission_usd: float,
    trade_date: str,
) -> None:
    """Validate transaction fields.  Raises TransactionError on failure."""
    if not ticker or not isinstance(ticker, str):
        raise TransactionError("ticker is required")
    if action not in ("BUY", "SELL"):
        raise TransactionError(f"action must be BUY or SELL, got {action!r}")
    if not isinstance(quantity, (int, float)) or quantity <= 0:
        raise TransactionError("quantity must be greater than 0")
    if not isinstance(price_usd, (int, float)) or price_usd < 0:
        raise TransactionError("price_usd must be >= 0")
    if not isinstance(commission_usd, (int, float)) or commission_usd < 0:
        raise TransactionError("commission_usd must be >= 0")
    if not trade_date or not isinstance(trade_date, str):
        raise TransactionError("trade_date is required")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)


# ── CRUD ─────────────────────────────────────────────────────────────────────

def add_transaction(
    conn: sqlite3.Connection,
    *,
    trade_date: str,
    ticker: str,
    action: str,
    quantity: float,
    price_usd: float,
    commission_usd: float = 0.0,
    note: str | None = None,
) -> dict[str, Any]:
    """Insert a new transaction and return it as a dict."""
    _validate_transaction(ticker, action, quantity, price_usd, commission_usd, trade_date)
    now = _now_iso()
    ticker = ticker.upper().strip()
    cur = conn.execute(
        "INSERT INTO transactions "
        "(trade_date, ticker, action, quantity, price_usd, commission_usd, note, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (trade_date, ticker, action, quantity, price_usd, commission_usd, note, now, now),
    )
    conn.commit()
    assert cur.lastrowid is not None
    result = get_transaction(conn, cur.lastrowid)
    assert result is not None
    return result


def get_transaction(conn: sqlite3.Connection, tx_id: int) -> dict[str, Any] | None:
    """Return a single transaction by id, or None."""
    row = conn.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_transactions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all transactions ordered by date, then id."""
    rows = conn.execute(
        "SELECT * FROM transactions ORDER BY trade_date, id"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_transactions_by_ticker(conn: sqlite3.Connection, ticker: str) -> list[dict[str, Any]]:
    """Return transactions for a specific ticker, ordered by date."""
    ticker = ticker.upper().strip()
    rows = conn.execute(
        "SELECT * FROM transactions WHERE ticker = ? ORDER BY trade_date, id",
        (ticker,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_transaction(
    conn: sqlite3.Connection,
    tx_id: int,
    *,
    trade_date: str | None = None,
    ticker: str | None = None,
    action: str | None = None,
    quantity: float | None = None,
    price_usd: float | None = None,
    commission_usd: float | None = None,
    note: str | None = None,
) -> dict[str, Any] | None:
    """Update an existing transaction.  Returns the updated row or None."""
    existing = get_transaction(conn, tx_id)
    if existing is None:
        return None

    fields = {
        "trade_date": trade_date if trade_date is not None else existing["trade_date"],
        "ticker": (ticker.upper().strip() if ticker is not None else existing["ticker"]),
        "action": action if action is not None else existing["action"],
        "quantity": quantity if quantity is not None else existing["quantity"],
        "price_usd": price_usd if price_usd is not None else existing["price_usd"],
        "commission_usd": commission_usd if commission_usd is not None else existing["commission_usd"],
        "note": note if note is not None else existing["note"],
    }

    _validate_transaction(
        fields["ticker"], fields["action"], fields["quantity"],
        fields["price_usd"], fields["commission_usd"], fields["trade_date"],
    )

    # The trigger handles updated_at automatically.
    conn.execute(
        "UPDATE transactions SET "
        "trade_date = ?, ticker = ?, action = ?, quantity = ?, "
        "price_usd = ?, commission_usd = ?, note = ? "
        "WHERE id = ?",
        (
            fields["trade_date"], fields["ticker"], fields["action"],
            fields["quantity"], fields["price_usd"], fields["commission_usd"],
            fields["note"], tx_id,
        ),
    )
    conn.commit()
    return get_transaction(conn, tx_id)


def delete_transaction(conn: sqlite3.Connection, tx_id: int) -> bool:
    """Delete a transaction by id.  Returns True if it existed."""
    existing = get_transaction(conn, tx_id)
    if existing is None:
        return False
    conn.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    return True
