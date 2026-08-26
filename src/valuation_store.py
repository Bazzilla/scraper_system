"""Historical snapshot store for the valuation validation-mode.

Append-only SQLite store (one row per symbol per day) collecting the
valuation observations (upside_pct + multiples) so that, once enough
history is accumulated, an EMPIRICAL validation report can decide whether
to promote the data into the strategy score.

This is deliberately decoupled from the signal pipeline: nothing here ever
touches VALUTA INGRESSO / OSSERVA / ATTENDI. The only human decision is:
- now: keep display-only;
- later (with enough data): promote or not, based on the validation report.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_HISTORY_PATH = "output/valuation_history.db"

# Bucket descrittivi automatici sull'upside vs target mediano analisti.
# Soglie più fini del semaforo del report: servono alla validazione empirica.
BUCKETS: list[tuple[float, str, str]] = [
    (30.0, "deep_discount", "sconto profondo"),
    (10.0, "discount", "sconto"),
    (-10.0, "fair", "equo"),
    (float("-inf"), "premium", "caro"),
]


def bucket_for(upside_pct: float | None) -> str | None:
    """Descriptive bucket from the upside percentage (None → None).

    Soglie: ≥+30 deep_discount · +10..+30 discount · -10..+10 fair (escluso
    -10 esatto) · <-10 premium.
    """
    if upside_pct is None:
        return None
    if upside_pct >= 30:
        return "deep_discount"
    if upside_pct >= 10:
        return "discount"
    if upside_pct > -10:
        return "fair"
    return "premium"


def bucket_label(key: str | None) -> str | None:
    """Italian display label for a bucket key."""
    if key is None:
        return None
    for _threshold, bkey, label in BUCKETS:
        if bkey == key:
            return label
    return None


def init_db(conn: sqlite3.Connection) -> None:
    """Create the snapshots table if missing."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snap_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            category TEXT,
            upside_pct REAL,
            trailing_pe REAL,
            forward_pe REAL,
            price_to_book REAL,
            ev_ebitda REAL,
            peg_ratio REAL,
            current_price REAL,
            target_median REAL,
            bucket TEXT,
            UNIQUE(snap_date, symbol)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_symbol "
        "ON snapshots(symbol, snap_date)"
    )


def append_snapshots(
    db_path: str,
    result: dict[str, Any],
    snap_date: str | None = None,
) -> int:
    """Persist one snapshot per fresh ticker from a valuation run output.

    ``result`` is the valuation module output ({category: {symbol: {...}}}
    plus module-level status). Re-running on the same day REPLACES the
    day's rows (UNIQUE(snap_date, symbol)) — no duplicates. Returns the
    number of rows written.
    """
    snap_date = snap_date or datetime.now(timezone.utc).date().isoformat()
    fields = (
        "upside_pct", "trailing_pe", "forward_pe", "price_to_book",
        "ev_ebitda", "peg_ratio", "current_price", "target_median",
    )
    rows: list[tuple[Any, ...]] = []
    for category, entries in result.items():
        if not isinstance(entries, dict):
            continue  # module-level "status"/"origin"
        for symbol, data in entries.items():
            if not isinstance(data, dict) or data.get("status") != "fresh":
                continue
            bucket = bucket_for(data.get("upside_pct"))
            rows.append((
                snap_date, symbol, category,
                *(data.get(f) for f in fields),
                bucket,
            ))

    if not rows:
        return 0

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        init_db(conn)
        conn.executemany(
            "INSERT OR REPLACE INTO snapshots "
            "(snap_date, symbol, category, upside_pct, trailing_pe, forward_pe,"
            " price_to_book, ev_ebitda, peg_ratio, current_price, target_median,"
            " bucket) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
    return len(rows)


def load_history(db_path: str, symbol: str | None = None) -> list[dict[str, Any]]:
    """Load snapshots (optionally filtered by symbol), oldest first."""
    path = Path(db_path)
    if not path.exists():
        return []
    query = "SELECT * FROM snapshots"
    params: tuple[Any, ...] = ()
    if symbol:
        query += " WHERE symbol = ?"
        params = (symbol,)
    query += " ORDER BY snap_date, symbol"
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(query, params)]


def summarize(db_path: str) -> dict[str, Any]:
    """Aggregate the collected history for the empirical validation report."""
    if not Path(db_path).exists():
        return {"days": 0, "symbols": 0, "note": "nessuno storico raccolto"}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        days, first, last = conn.execute(
            "SELECT COUNT(DISTINCT snap_date), MIN(snap_date), MAX(snap_date)"
            " FROM snapshots"
        ).fetchone()
        symbols = conn.execute(
            "SELECT COUNT(DISTINCT symbol) FROM snapshots"
        ).fetchone()[0]
        buckets = {
            row["bucket"]: row["n"]
            for row in conn.execute(
                "SELECT bucket, COUNT(*) AS n FROM snapshots"
                " GROUP BY bucket ORDER BY n DESC"
            )
        }
        per_symbol_min = conn.execute(
            "SELECT MIN(c) FROM (SELECT COUNT(DISTINCT snap_date) AS c"
            " FROM snapshots GROUP BY symbol)"
        ).fetchone()[0]
    return {
        "days": days,
        "first": first,
        "last": last,
        "symbols": symbols,
        "min_days_per_symbol": per_symbol_min,
        "buckets": buckets,
    }


def format_report(summary: dict[str, Any]) -> str:
    """Render the human-readable validation-mode status report."""
    if not summary.get("days"):
        return "Validation-mode valuation: nessuno storico ancora raccolto."
    lines = [
        "=== Valuation validation-mode: stato raccolta ===",
        f"Giorni raccolti: {summary['days']}"
        f" ({summary['first']} → {summary['last']})",
        f"Simboli coperti: {summary['symbols']}"
        f" (min giorni/simbolo: {summary.get('min_days_per_symbol')})",
        "Distribuzione bucket (osservazioni totali):",
    ]
    for key, count in sorted(summary.get("buckets", {}).items(), key=lambda kv: -kv[1]):
        lines.append(f"  - {key} ({bucket_label(key)}): {count}")
    lines.append(
        "\nPromozione nello score: decidere SOLO con storico sufficiente "
        "(vedi criterio di validazione empirica). Dati attualmente display-only."
    )
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover - CLI di consultazione
    import argparse

    parser = argparse.ArgumentParser(description="Valuation history report")
    parser.add_argument("--db", default=DEFAULT_HISTORY_PATH)
    args = parser.parse_args()
    print(format_report(summarize(args.db)))
