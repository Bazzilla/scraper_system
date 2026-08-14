"""Unit tests for the AAII scraper module (pure functions only)."""

from __future__ import annotations

import unittest
from unittest import mock

from scrapers.aaii_scraper import (
    build_result,
    parse_data_chart,
    parse_html_bars,
    run,
)


class TestParseDataChart(unittest.TestCase):
    def test_parses_current_week(self):
        html = (
            "var dataChart5 =\n"
            '[{"date_": "2026-08-05", "bullish": "37", "bearish": "38", '
            '"neutral": "25", "spread": "-1"},\n'
            '{"date_": "2026-07-29", "bullish": "31", "bearish": "42", '
            '"neutral": "26"}];'
        )
        result = parse_data_chart(html)
        self.assertEqual(result["bullish"], 37.0)
        self.assertEqual(result["bearish"], 38.0)
        self.assertEqual(result["neutral"], 25.0)

    def test_raises_when_json_missing(self):
        with self.assertRaises(ValueError):
            parse_data_chart("<html>no data</html>")

    def test_raises_when_empty(self):
        with self.assertRaises(ValueError):
            parse_data_chart("var dataChart5 = [];")


class TestParseHtmlBars(unittest.TestCase):
    def test_parses_bars(self):
        html = (
            '<div class="weekending"><div class="datebars">'
            '<div class="date">8/5/2026</div><div class="bars">'
            '<div class="bar bullish">37.0%</div>'
            '<div class="bar neutral">25.0%</div>'
            '<div class="bar bearish">38.0%</div>'
            "</div></div></div>"
        )
        result = parse_html_bars(html)
        self.assertEqual(result["bullish"], 37.0)
        self.assertEqual(result["neutral"], 25.0)
        self.assertEqual(result["bearish"], 38.0)

    def test_raises_when_bars_missing(self):
        with self.assertRaises(ValueError):
            parse_html_bars("<html><body>no bars</body></html>")


class TestBuildResult(unittest.TestCase):
    def test_builds_file_json_shape(self):
        result = build_result(37.0, 38.0, 25.0, "2026-08-07T14:00:00+00:00")
        self.assertEqual(result["bullish"], 37.0)
        self.assertEqual(result["bearish"], 38.0)
        self.assertEqual(result["neutral"], 25.0)
        self.assertEqual(result["frequency"], "weekly")
        self.assertEqual(result["stale_after_hours"], 168)
        self.assertEqual(result["status"], "fresh")
        self.assertIn("next_expected", result)


class TestRun(unittest.TestCase):
    def test_run_source_html_bars_when_both_present(self):
        # AAII ha rimosso dataChart5 (verificato 2026-08-14): html_bars è la
        # strategia primaria. Con entrambi i blocchi presenti vince html_bars.
        html = (
            "<div class=\"weekending\"><div class=\"datebars\">"
            "<div class=\"date\">8/14/2026</div><div class=\"bars\">"
            "<div class=\"bar bullish\">34.7%</div>"
            "<div class=\"bar neutral\">27.4%</div>"
            "<div class=\"bar bearish\">37.9%</div>"
            "</div></div></div>"
            "\nvar dataChart5 =\n"
            '[{"date_": "2026-08-13", "bullish": "30", "bearish": "40", '
            '"neutral": "30"}]'
        )
        with mock.patch(
            "scrapers.aaii_scraper._fetch_with_retry",
            return_value=html,
        ):
            result = run()
        self.assertEqual(result["source"], "html_bars")
        self.assertEqual(result["bullish"], 34.7)

    def test_run_source_data_chart(self):
        # HTML con solo dataChart5 (legacy) → source "data_chart"
        html = (
            "var dataChart5 =\n"
            '[{"date_": "2026-08-05", "bullish": "37", "bearish": "38", '
            '"neutral": "25", "spread": "-1"},\n'
            '{"date_": "2026-07-29", "bullish": "31", "bearish": "42", '
            '"neutral": "26"}];'
        )
        with mock.patch(
            "scrapers.aaii_scraper._fetch_with_retry",
            return_value=html,
        ):
            result = run()
        self.assertEqual(result["source"], "data_chart")
        self.assertEqual(result["bullish"], 37.0)
        self.assertEqual(result["bearish"], 38.0)
        self.assertEqual(result["neutral"], 25.0)
        self.assertEqual(result["status"], "fresh")

    def test_run_source_html_bars(self):
        # HTML con solo bars → source "html_bars"
        html = (
            '<div class="weekending"><div class="datebars">'
            '<div class="date">8/5/2026</div><div class="bars">'
            '<div class="bar bullish">37.0%</div>'
            '<div class="bar neutral">25.0%</div>'
            '<div class="bar bearish">38.0%</div>'
            "</div></div></div>"
        )
        with mock.patch(
            "scrapers.aaii_scraper._fetch_with_retry",
            return_value=html,
        ):
            result = run()
        self.assertEqual(result["source"], "html_bars")
        self.assertEqual(result["bullish"], 37.0)
        self.assertEqual(result["bearish"], 38.0)
        self.assertEqual(result["neutral"], 25.0)
        self.assertEqual(result["status"], "fresh")


if __name__ == "__main__":
    unittest.main()