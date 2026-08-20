"""Unit tests for the NYSE NH-NL scraper (Barchart highs/lows summary)."""

from __future__ import annotations

import unittest
from unittest import mock

import requests

from scrapers.nh_nl_scraper import (
    DEFAULT_STALE_AFTER_HOURS,
    build_result,
    fetch_page,
    parse_highs_lows,
    run,
)


def _anchor(period: str, val: int) -> str:
    """A desktop-table row: NYSE value is the 2nd data column (after OVERALL)."""
    return (
        f"<tr><td>{period}</td>"
        f'<td><a href="/stocks/highs-lows/summary?timeFrame=1y&screener=overall">{val}</a></td>'
        f'<td><a href="/stocks/highs-lows/summary?timeFrame=1y&screener=nyse">{val}</a></td>'
        f'<td><a href="/stocks/highs-lows/summary?timeFrame=1y&screener=nasdaq">{val}</a></td>'
        f'<td><a href="/stocks/highs-lows/summary?timeFrame=1y&screener=arca">{val}</a></td>'
        f'<td><a href="/stocks/highs-lows/summary?timeFrame=1y&screener=etf">{val}</a></td>'
        f'<td><a href="/stocks/highs-lows/summary?timeFrame=1y&screener=otc">{val}</a></td>'
        "</tr>"
    )


def _mobile_row(period: str, val: int) -> str:
    """Mobile duplicate: same labels but NO timeFrame anchors."""
    return (
        f"<tr><td>{period}</td>"
        f"<td>{val}</td><td>{val}</td><td>{val}</td>"
        f"<td>{val}</td><td>{val}</td><td>{val}</td>"
        "</tr>"
    )


def _sample_html() -> str:
    """Realistic Barchart summary page: desktop table + mobile duplicate."""
    desktop = "".join(
        _anchor(p, v)
        for p, v in [
            ("1-Month Highs", 250),
            ("1-Month Lows", 122),
            ("3-Month Highs", 172),
            ("3-Month Lows", 52),
            ("52-Week Highs", 64),
            ("52-Week Lows", 19),
            ("YTD Highs", 78),
            ("YTD Lows", 26),
            ("All-Time Highs", 24),
            ("All-Time Lows", 9),
        ]
    )
    mobile = "".join(
        _mobile_row(p, v)
        for p, v in [
            ("1-Month Highs", 250),
            ("1-Month Lows", 122),
            ("52-Week Highs", 64),
            ("52-Week Lows", 19),
        ]
    )
    return (
        '<html><head><title>Stocks Highs and Lows Summary</title></head><body>'
        f'<span class="last-updated">Last Updated: 08/19/2026 19:43 ET</span>'
        f'<table>{desktop}</table>'
        f'<table>{mobile}</table>'
        "</body></html>"
    )


class TestParseHighsLows(unittest.TestCase):
    def test_extracts_52w_highs_lows(self):
        data = parse_highs_lows(_sample_html())
        self.assertEqual(data["nyse_highs_52w"], 64)
        self.assertEqual(data["nyse_lows_52w"], 19)

    def test_ignores_mobile_duplicate(self):
        # Senza il filtro timeFrame il duplicato mobile introdurrebbe ambiguità;
        # il parser deve prendere solo la tabella desktop.
        data = parse_highs_lows(_sample_html())
        self.assertEqual(data["nyse_highs_52w"], 64)
        self.assertEqual(data["nyse_lows_52w"], 19)

    def test_extracts_trade_date(self):
        data = parse_highs_lows(_sample_html())
        self.assertEqual(data["trade_date"], "2026-08-19")

    def test_missing_52w_raises(self):
        html = "<table>" + _anchor("1-Month Highs", 250) + "</table>"
        with self.assertRaises(ValueError):
            parse_highs_lows(html)

    def test_no_table_raises(self):
        with self.assertRaises(ValueError):
            parse_highs_lows("<html><body>no data</body></html>")


class TestBuildResult(unittest.TestCase):
    def test_shape_and_defaults(self):
        data = {"nyse_highs_52w": 64, "nyse_lows_52w": 19, "trade_date": "2026-08-19"}
        result = build_result(data, fetched_at="2026-08-19T00:00:00+00:00")
        self.assertEqual(result["nyse_highs_52w"], 64)
        self.assertEqual(result["nyse_lows_52w"], 19)
        self.assertEqual(result["trade_date"], "2026-08-19")
        self.assertEqual(result["frequency"], "daily")
        self.assertEqual(result["stale_after_hours"], DEFAULT_STALE_AFTER_HOURS)
        self.assertEqual(result["status"], "fresh")

    def test_custom_stale_after_hours(self):
        result = build_result({}, stale_after_hours=48)
        self.assertEqual(result["stale_after_hours"], 48)


class TestRun(unittest.TestCase):
    def test_run_returns_fresh_result(self):
        with mock.patch(
            "scrapers.nh_nl_scraper.fetch_page", return_value=_sample_html()
        ) as mock_fetch:
            result = run()
        mock_fetch.assert_called_once()
        self.assertEqual(result["nyse_highs_52w"], 64)
        self.assertEqual(result["nyse_lows_52w"], 19)
        self.assertEqual(result["status"], "fresh")

    def test_run_sends_browser_headers(self):
        class _FakeResponse:
            text = _sample_html()

            def raise_for_status(self):
                pass

        with mock.patch(
            "scrapers.nh_nl_scraper.requests.Session"
        ) as mock_session_cls:
            session = mock_session_cls.return_value.__enter__.return_value
            session.get.return_value = _FakeResponse()
            run()
        session.headers.update.assert_called_once()
        headers = session.headers.update.call_args[0][0]
        self.assertIn("User-Agent", headers)
        self.assertIn("Referer", headers)

    def test_fetch_page_raises_on_http_error(self):
        session = requests.Session()
        with self.assertRaises(requests.RequestException):
            fetch_page(session, url="https://invalid.invalid/", timeout=2)


if __name__ == "__main__":
    unittest.main()
