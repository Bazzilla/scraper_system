"""Unit tests for the valuation historical snapshot store (validation-mode)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from valuation_store import (
    append_snapshots,
    bucket_for,
    bucket_label,
    format_report,
    load_history,
    summarize,
)


def _result(upside: float | None = 25.0, status: str = "fresh"):
    return {
        "semiconductors": {
            "AMAT": {
                "symbol": "AMAT", "name": "Applied Materials", "status": status,
                "upside_pct": upside, "trailing_pe": 25.4, "forward_pe": 22.1,
                "price_to_book": 6.2, "ev_ebitda": 18.3, "peg_ratio": 1.4,
                "current_price": 100.0, "target_median": 125.0,
                "bucket": bucket_for(upside),
            },
        },
        "status": "fresh",
    }


class TestBuckets(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(bucket_for(35.0), "deep_discount")
        self.assertEqual(bucket_for(30.0), "deep_discount")
        self.assertEqual(bucket_for(15.0), "discount")
        self.assertEqual(bucket_for(10.0), "discount")
        self.assertEqual(bucket_for(0.0), "fair")
        self.assertEqual(bucket_for(-9.9), "fair")
        self.assertEqual(bucket_for(-10.0), "premium")
        self.assertIsNone(bucket_for(None))

    def test_labels(self):
        self.assertEqual(bucket_label("deep_discount"), "sconto profondo")
        self.assertEqual(bucket_label("premium"), "caro")
        self.assertIsNone(bucket_label(None))


class TestAppendSnapshots(unittest.TestCase):
    def test_append_and_dedupe_same_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "history.db")
            n1 = append_snapshots(db, _result(), snap_date="2026-08-26")
            n2 = append_snapshots(
                db, _result(upside=35.0), snap_date="2026-08-26"
            )
            self.assertEqual(n1, 1)
            self.assertEqual(n2, 1)  # REPLACE, non duplicato
            history = load_history(db)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["upside_pct"], 35.0)  # ultima vince
            self.assertEqual(history[0]["bucket"], "deep_discount")

    def test_different_days_accumulate(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "history.db")
            append_snapshots(db, _result(), snap_date="2026-08-25")
            append_snapshots(db, _result(), snap_date="2026-08-26")
            self.assertEqual(len(load_history(db)), 2)

    def test_skips_non_fresh_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "history.db")
            n = append_snapshots(db, _result(status="error"), snap_date="2026-08-26")
            self.assertEqual(n, 0)
            self.assertEqual(load_history(db), [])


class TestSummarize(unittest.TestCase):
    def test_summary_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "history.db")
            append_snapshots(db, _result(upside=35.0), snap_date="2026-08-25")
            append_snapshots(db, _result(upside=15.0), snap_date="2026-08-26")
            summary = summarize(db)
            self.assertEqual(summary["days"], 2)
            self.assertEqual(summary["symbols"], 1)
            self.assertEqual(summary["min_days_per_symbol"], 2)
            self.assertIn("discount", summary["buckets"])
            report = format_report(summary)
            self.assertIn("Giorni raccolti: 2", report)
            self.assertIn("display-only", report)

    def test_summary_empty_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = summarize(str(Path(tmp) / "missing.db"))
            self.assertEqual(summary["days"], 0)
            self.assertIn("nessuno storico", format_report(summary))


if __name__ == "__main__":
    unittest.main()
