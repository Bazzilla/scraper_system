"""Unit tests for the PCT SMA scraper (breadth, pure functions)."""

from __future__ import annotations

import json
import tempfile
import unittest
from typing import Any

from scrapers.pct_sma_scraper import aggregate, build_result, load_cache


def _records(n: int = 60, price: float = 100.0) -> list[dict[str, Any]]:
    """Records with constant price → above SMA50/200 (last close == sma)."""
    import pandas as pd
    return [
        {
            "date": pd.Timestamp(d).strftime("%Y-%m-%d"),
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": 1000,
        }
        for d in pd.date_range("2026-01-01", periods=n, freq="D")
    ]


def _rising_records(n: int = 60) -> list[dict[str, Any]]:
    """Records rising to 110 → above SMA50 (last close > sma50)."""
    import pandas as pd
    return [
        {
            "date": pd.Timestamp(d).strftime("%Y-%m-%d"),
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0 + i * 0.2,  # sale gradualmente
            "volume": 1000,
        }
        for i, d in enumerate(pd.date_range("2026-01-01", periods=n, freq="D"))
    ]


class TestLoadCache(unittest.TestCase):
    def test_loads_cache(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"semiconductors": {"AMAT": _records(5)}}, fh)
            path = fh.name
        cache = load_cache(path)
        self.assertIn("AMAT", cache["semiconductors"])

    def test_missing_cache_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_cache("/nonexistent/cache.json")


class TestAggregate(unittest.TestCase):
    def test_aggregates_per_category_and_total(self):
        tickers = {
            "semiconductors": [{"symbol": "AMAT", "name": "A"}],
            "defense": [{"symbol": "RTX", "name": "R"}],
        }
        cache = {
            "semiconductors": {"AMAT": _rising_records()},   # sopra SMA50
            "defense": {"RTX": _records()},                   # uguale a SMA50 (>= ok)
        }
        result = aggregate(tickers, cache)
        semi = result["semiconductors"]
        self.assertEqual(semi["total"], 1)
        self.assertEqual(semi["above_sma50"], 1)
        self.assertEqual(semi["pct_sma50"], 100.0)
        # 60 record → SMA200 None → above_sma200 resta 0
        self.assertEqual(semi["above_sma200"], 0)
        self.assertEqual(semi["pct_sma200"], 0.0)
        total = result["total"]
        self.assertEqual(total["total"], 2)
        self.assertEqual(total["above_sma50"], 2)
        self.assertEqual(total["pct_sma50"], 100.0)

    def test_sma200_counted_with_sufficient_data(self):
        tickers = {"semiconductors": [{"symbol": "AMAT", "name": "A"}]}
        cache = {"semiconductors": {"AMAT": _records(220)}}  # >= 200 → SMA200 valida
        result = aggregate(tickers, cache)
        semi = result["semiconductors"]
        self.assertEqual(semi["total"], 1)
        self.assertEqual(semi["above_sma50"], 1)
        self.assertEqual(semi["above_sma200"], 1)
        self.assertEqual(semi["pct_sma200"], 100.0)

    def test_partial_data_sma50_valid_sma200_none(self):
        tickers = {"semiconductors": [{"symbol": "AMAT", "name": "A"}]}
        cache = {"semiconductors": {"AMAT": _records(80)}}  # 50-199 → solo SMA50
        result = aggregate(tickers, cache)
        semi = result["semiconductors"]
        self.assertEqual(semi["total"], 1)
        self.assertEqual(semi["above_sma50"], 1)
        self.assertEqual(semi["above_sma200"], 0)

    def test_ticker_with_insufficient_data_excluded(self):
        tickers = {"semiconductors": [{"symbol": "AMAT", "name": "A"}]}
        cache = {"semiconductors": {"AMAT": _records(5)}}  # < 50 record → escluso
        result = aggregate(tickers, cache)
        self.assertEqual(result["total"]["total"], 0)
        self.assertEqual(result["total"]["pct_sma50"], 0.0)


class TestBuildResult(unittest.TestCase):
    def test_builds_file_json_shape(self):
        agg = {
            "semiconductors": {"above_sma50": 1, "total": 1, "pct_sma50": 100.0,
                               "above_sma200": 1, "pct_sma200": 100.0},
            "total": {"above_sma50": 1, "total": 1, "pct_sma50": 100.0,
                      "above_sma200": 1, "pct_sma200": 100.0},
        }
        result = build_result(agg, fetched_at="2026-08-12T00:00:00+00:00")
        self.assertEqual(result["total"]["pct_sma50"], 100.0)
        self.assertEqual(result["frequency"], "daily")
        self.assertEqual(result["status"], "fresh")

    def test_empty_cache_gives_stale_status(self):
        agg = {
            "semiconductors": {"above_sma50": 0, "total": 0, "pct_sma50": 0.0,
                               "above_sma200": 0, "pct_sma200": 0.0},
            "total": {"above_sma50": 0, "total": 0, "pct_sma50": 0.0,
                      "above_sma200": 0, "pct_sma200": 0.0},
        }
        result = build_result(agg, fetched_at="2026-08-12T00:00:00+00:00")
        self.assertEqual(result["status"], "stale")


if __name__ == "__main__":
    unittest.main()
