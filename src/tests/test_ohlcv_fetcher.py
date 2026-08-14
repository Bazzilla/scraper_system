"""Unit tests for the OHLCV fetcher scraper (pure functions, no network)."""

from __future__ import annotations

import unittest
from unittest import mock

import pandas as pd

from scrapers.ohlcv_fetcher import (
    _fetch_all,
    build_result,
    frame_to_records,
    serialize_cache,
)


def _sample_frame() -> pd.DataFrame:
    index = pd.to_datetime(["2026-08-07", "2026-08-08"])
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.5, 102.5],
            "Volume": [1000, 1100],
        },
        index=index,
    )


class TestFrameToRecords(unittest.TestCase):
    def test_converts_frame_to_records(self):
        records = frame_to_records(_sample_frame())
        self.assertEqual(len(records), 2)
        first = records[0]
        self.assertEqual(first["date"], "2026-08-07")
        self.assertEqual(first["open"], 100.0)
        self.assertEqual(first["high"], 102.0)
        self.assertEqual(first["low"], 99.0)
        self.assertEqual(first["close"], 101.5)
        self.assertEqual(first["volume"], 1000)

    def test_drops_nan_rows(self):
        frame = _sample_frame()
        frame.loc[frame.index[0], "Volume"] = float("nan")
        records = frame_to_records(frame)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["date"], "2026-08-08")


class TestSerializeCache(unittest.TestCase):
    def test_serializes_nested_cache(self):
        cache = {
            "semiconductors": {
                "AMAT": [{"date": "2026-08-07", "close": 101.5}]
            }
        }
        text = serialize_cache(cache)
        self.assertIn('"AMAT"', text)
        self.assertIn("2026-08-07", text)


class TestBuildResult(unittest.TestCase):
    def test_builds_output_shape(self):
        tickers = {"semiconductors": [{"symbol": "AMAT", "name": "Applied Materials"}]}
        cache = {
            "semiconductors": {
                "AMAT": [{"date": "2026-08-07", "close": 101.5}]
            }
        }
        result = build_result(tickers, cache, fetched_at="2026-08-08T00:00:00+00:00")
        amat = result["semiconductors"]["AMAT"]
        self.assertEqual(amat["symbol"], "AMAT")
        self.assertEqual(amat["last_close"], 101.5)
        self.assertEqual(amat["last_date"], "2026-08-07")
        self.assertEqual(result["status"], "fresh")

    def test_error_ticker_is_skipped(self):
        tickers = {"semiconductors": [{"symbol": "AMAT", "name": "A"}]}
        cache = {"semiconductors": {}}
        result = build_result(tickers, cache)
        self.assertNotIn("AMAT", result["semiconductors"])
        self.assertEqual(result["status"], "stale")


class TestFetchAll(unittest.TestCase):
    def test_applies_request_delay_between_tickers(self):
        tickers = {
            "semiconductors": [
                {"symbol": "AMAT", "name": "Applied Materials"},
                {"symbol": "LRCX", "name": "Lam Research"},
            ]
        }
        config = {"request_delay": 0.5}
        with (
            mock.patch(
                "scrapers.ohlcv_fetcher._fetch_ticker_with_retry",
                return_value=_sample_frame(),
            ) as mock_fetch,
            mock.patch("scrapers.ohlcv_fetcher.time.sleep") as mock_sleep,
        ):
            cache = _fetch_all(tickers, config)
        self.assertEqual(mock_fetch.call_count, 2)
        # sleep chiamato una volta per ticker (dopo ogni fetch)
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertEqual(mock_sleep.call_args_list[0].args, (0.5,))
        self.assertIn("AMAT", cache["semiconductors"])
        self.assertIn("LRCX", cache["semiconductors"])

    def test_zero_request_delay_skips_sleep(self):
        tickers = {"semiconductors": [{"symbol": "AMAT", "name": "A"}]}
        config = {"request_delay": 0}
        with (
            mock.patch(
                "scrapers.ohlcv_fetcher._fetch_ticker_with_retry",
                return_value=_sample_frame(),
            ),
            mock.patch("scrapers.ohlcv_fetcher.time.sleep") as mock_sleep,
        ):
            _fetch_all(tickers, config)
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
