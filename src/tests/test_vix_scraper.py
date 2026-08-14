"""Unit tests for the VIX scraper module (pure functions only)."""

from __future__ import annotations

import unittest

from scrapers.vix_scraper import build_result, parse_csv


class TestParseCsv(unittest.TestCase):
    def test_parses_latest_close(self):
        csv_text = (
            "DATE,OPEN,HIGH,LOW,CLOSE\n"
            "08/05/2026,20.0,21.0,19.5,20.5\n"
            "08/06/2026,20.5,22.0,20.0,21.75\n"
        )
        result = parse_csv(csv_text)
        self.assertEqual(result["vix_close"], 21.75)
        self.assertEqual(result["date"], "08/06/2026")

    def test_raises_when_empty(self):
        with self.assertRaises(ValueError):
            parse_csv("DATE,OPEN,HIGH,LOW,CLOSE\n")


class TestBuildResult(unittest.TestCase):
    def test_builds_file_json_shape(self):
        result = build_result(21.75, "2026-08-07T08:00:00+00:00")
        self.assertEqual(result["vix_close"], 21.75)
        self.assertEqual(result["frequency"], "daily")
        self.assertEqual(result["stale_after_hours"], 24)
        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["fetched_at"], "2026-08-07T08:00:00+00:00")


if __name__ == "__main__":
    unittest.main()