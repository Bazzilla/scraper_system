"""Unit tests for the fair-value / valuation scraper module."""

from __future__ import annotations

import unittest
from unittest import mock

from report_helpers import semaphore_class
from scrapers.valuation import build_result, extract_valuation, run


def _info(**overrides):
    base = {
        "currentPrice": 100.0,
        "trailingPE": 25.4,
        "forwardPE": 22.1,
        "priceToBook": 6.2,
        "enterpriseToEbitda": 18.3,
        "trailingPegRatio": 1.4,
        "targetMeanPrice": 130.0,
        "targetMedianPrice": 125.0,
        "targetHighPrice": 160.0,
        "targetLowPrice": 90.0,
    }
    base.update(overrides)
    return base


TICKERS = {"semiconductors": [{"symbol": "AMAT", "name": "Applied Materials"}]}


class TestExtractValuation(unittest.TestCase):
    def test_computes_upside_from_median_target(self):
        data = extract_valuation(_info())
        # (125 - 100) / 100 * 100 = +25%
        self.assertEqual(data["upside_pct"], 25.0)
        self.assertEqual(data["trailingPE"], 25.4)
        self.assertEqual(data["targetMedianPrice"], 125.0)

    def test_missing_target_or_price_gives_none_upside(self):
        self.assertIsNone(extract_valuation(_info(targetMedianPrice=None))["upside_pct"])
        self.assertIsNone(extract_valuation(_info(currentPrice=None))["upside_pct"])

    def test_falls_back_to_regular_market_price(self):
        data = extract_valuation(_info(currentPrice=None, regularMarketPrice=100.0))
        self.assertEqual(data["current_price"], 100.0)
        self.assertEqual(data["upside_pct"], 25.0)

    def test_empty_info_all_none(self):
        data = extract_valuation({})
        self.assertIsNone(data["upside_pct"])
        self.assertIsNone(data["forwardPE"])


class TestBuildResult(unittest.TestCase):
    def test_shape_and_status(self):
        fetched = {"semiconductors": {"AMAT": extract_valuation(_info())}}
        result = build_result(TICKERS, fetched, fetched_at="2026-08-26T10:00:00+00:00")
        row = result["semiconductors"]["AMAT"]
        self.assertEqual(row["symbol"], "AMAT")
        self.assertEqual(row["status"], "fresh")
        self.assertEqual(row["upside_pct"], 25.0)
        self.assertEqual(result["status"], "fresh")

    def test_fail_closed_when_ticker_missing(self):
        result = build_result(TICKERS, {"semiconductors": {}}, fetched_at="x")
        self.assertNotIn("AMAT", result["semiconductors"])
        self.assertEqual(result["status"], "stale")


class TestRun(unittest.TestCase):
    def test_run_with_mocked_fetch_and_delay(self):
        with mock.patch(
            "scrapers.valuation.fetch_info", return_value=_info()
        ) as mock_fetch, mock.patch("scrapers.valuation.time.sleep") as mock_sleep:
            result = run({"tickers": TICKERS, "request_delay": 0})
        mock_fetch.assert_called_once_with("AMAT")
        mock_sleep.assert_not_called()  # request_delay=0
        self.assertEqual(result["semiconductors"]["AMAT"]["upside_pct"], 25.0)

    def test_per_ticker_error_isolation(self):
        calls = {"n": 0}

        def _flaky(symbol):
            calls["n"] += 1
            raise RuntimeError("yahoo down")

        with mock.patch("scrapers.valuation.fetch_info", side_effect=_flaky), \
             mock.patch("scrapers.valuation.time.sleep"):
            result = run({"tickers": TICKERS, "retries": 1, "request_delay": 0})
        # Fail-closed: il ticker sparisce dalla categoria, status stale
        self.assertNotIn("AMAT", result["semiconductors"])
        self.assertEqual(result["status"], "stale")


class TestUpsideSemaphore(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(semaphore_class(25.0, "upside"), "ok")
        self.assertEqual(semaphore_class(20.0, "upside"), "ok")
        self.assertEqual(semaphore_class(5.0, "upside"), "neutral")
        self.assertEqual(semaphore_class(-9.9, "upside"), "neutral")
        self.assertEqual(semaphore_class(-10.0, "upside"), "critical")


if __name__ == "__main__":
    unittest.main()
