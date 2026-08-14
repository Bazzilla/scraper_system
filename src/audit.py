"""SQLite audit log for scraper executions.

Records what was scraped, when, and the outcome. DB connection is injected
for testability (e.g. in-memory SQLite).
"""

from __future__ import annotations

import sqlite3
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scraper TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT
)
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Create the audit table if it does not exist."""
    conn.execute(_SCHEMA)
    conn.commit()


def record_execution(
    conn: sqlite3.Connection,
    scraper: str,
    executed_at: str,
    status: str,
    error: str | None = None,
) -> None:
    """Insert one audit record for a scraper execution."""
    conn.execute(
        "INSERT INTO executions (scraper, executed_at, status, error) "
        "VALUES (?, ?, ?, ?)",
        (scraper, executed_at, status, error),
    )
    conn.commit()