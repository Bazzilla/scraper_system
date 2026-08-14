"""Unit tests for the PCR scraper (pure functions, no network)."""

from __future__ import annotations

import unittest

from scrapers.pcr_scraper import build_result, parse_ratios

# HTML mock con il JSON embeddata escapato come da CBOE (Next.js __next_f).
# La struttura reale ha "ratios" seguito da "SUM OF ALL PRODUCTS" e selectedDate.
_HTML_SAMPLE = """
<script>self.__next_f.push([1,"24:[\\"$\\",\\"$L32\\",null,{\\"data\\":{\\"optionsData\\":{\\"ratios\\":[{\\"name\\":\\"TOTAL PUT/CALL RATIO\\",\\"value\\":\\"0.81\\"},{\\"name\\":\\"INDEX PUT/CALL RATIO\\",\\"value\\":\\"0.90\\"},{\\"name\\":\\"EXCHANGE TRADED PRODUCTS PUT/CALL RATIO\\",\\"value\\":\\"0.87\\"},{\\"name\\":\\"EQUITY PUT/CALL RATIO\\",\\"value\\":\\"0.63\\"},{\\"name\\":\\"CBOE VOLATILITY INDEX (VIX) PUT/CALL RATIO\\",\\"value\\":\\"0.20\\"}],\\"SUM OF ALL PRODUCTS\\":[{\\"name\\":\\"VOLUME\\",\\"call\\":0,\\"put\\":0,\\"total\\":0}],\\"selectedDate\\":\\"2026-08-11\\",\\"minDate\\":\\"2019-10-07\\"}]"])</script>
"""


class TestParseRatios(unittest.TestCase):
    def test_parses_equity_pcr(self):
        data = parse_ratios(_HTML_SAMPLE)
        self.assertEqual(data["equity_pcr"], 0.63)
        self.assertEqual(data["total_pcr"], 0.81)
        self.assertEqual(data["index_pcr"], 0.90)
        self.assertEqual(data["trade_date"], "2026-08-11")

    def test_missing_ratios_raises(self):
        with self.assertRaises(ValueError):
            parse_ratios("<html><body>no data here</body></html>")


class TestBuildResult(unittest.TestCase):
    def test_builds_file_json_shape(self):
        data = {"equity_pcr": 0.63, "total_pcr": 0.81, "index_pcr": 0.90,
                "trade_date": "2026-08-11"}
        result = build_result(data, fetched_at="2026-08-12T00:00:00+00:00")
        self.assertEqual(result["equity_pcr"], 0.63)
        self.assertEqual(result["trade_date"], "2026-08-11")
        self.assertEqual(result["frequency"], "daily")
        self.assertEqual(result["stale_after_hours"], 24)
        self.assertEqual(result["status"], "fresh")


if __name__ == "__main__":
    unittest.main()
