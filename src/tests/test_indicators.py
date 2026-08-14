"""Unit tests for the indicators scraper (pure functions, no network)."""

from __future__ import annotations

import json
import tempfile
import unittest
from typing import Any

import pandas as pd

from scrapers.indicators import (
    build_result,
    compute_indicators,
    load_cache,
    records_to_frame,
)


def _constant_frame(n: int = 60, price: float = 100.0) -> pd.DataFrame:
    """A frame with constant close price → RSI/SMA are well-defined."""
    index = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "Open": [price] * n,
            "High": [price] * n,
            "Low": [price] * n,
            "Close": [price] * n,
            "Volume": [1000] * n,
        },
        index=index,
    )


def _records(n: int = 60, price: float = 100.0) -> list[dict[str, Any]]:
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


class TestRecordsToFrame(unittest.TestCase):
    def test_converts_records_to_frame(self):
        frame = records_to_frame(_records(5))
        self.assertEqual(len(frame), 5)
        self.assertEqual(frame["Close"].iloc[-1], 100.0)


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


class TestComputeIndicators(unittest.TestCase):
    def test_constant_price_gives_known_values(self):
        frame = _constant_frame(n=252)
        ind = compute_indicators(frame)
        # SMA of constant series equals the price
        self.assertAlmostEqual(ind["sma_50"], 100.0, places=4)
        self.assertAlmostEqual(ind["sma_200"], 100.0, places=4)  # NaN if < 200 rows
        self.assertIn("rsi_14", ind)
        self.assertIn("obv", ind)
        self.assertIn("mfi_14", ind)
        self.assertIn("drawdown_52w", ind)


class TestBuildResult(unittest.TestCase):
    def test_builds_output_shape(self):
        tickers = {"semiconductors": [{"symbol": "AMAT", "name": "A"}]}
        indicators = {"AMAT": {"rsi_14": 50.0, "obv": 100, "mfi_14": 50.0,
                               "sma_50": 100.0, "sma_200": None,
                               "drawdown_52w": 0.0}}
        result = build_result(tickers, indicators, fetched_at="2026-08-08T00:00:00+00:00")
        amat = result["semiconductors"]["AMAT"]
        self.assertEqual(amat["rsi_14"], 50.0)
        self.assertEqual(amat["status"], "fresh")
        self.assertEqual(result["status"], "fresh")


if __name__ == "__main__":
    unittest.main()
