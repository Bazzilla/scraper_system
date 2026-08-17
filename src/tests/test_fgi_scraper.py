"""Unit tests for the FGI scraper module (pure functions + run chain)."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from scrapers.fgi_scraper import (
    build_result,
    parse_cnn,
    parse_components,
    parse_feargreedindex,
    parse_feargreedmeter,
    parse_html,
    parse_score,
    run,
    zone_from_score,
)


class TestZoneFromScore(unittest.TestCase):
    def test_extreme_fear(self):
        self.assertEqual(zone_from_score(10.0), "extreme fear")

    def test_fear(self):
        self.assertEqual(zone_from_score(30.0), "fear")

    def test_neutral(self):
        self.assertEqual(zone_from_score(50.0), "neutral")

    def test_greed(self):
        self.assertEqual(zone_from_score(60.0), "greed")

    def test_extreme_greed(self):
        self.assertEqual(zone_from_score(90.0), "extreme greed")

    def test_boundary_low(self):
        self.assertEqual(zone_from_score(25.0), "fear")

    def test_boundary_high(self):
        self.assertEqual(zone_from_score(100.0), "extreme greed")

    def test_strategy_boundary_neutral_greed(self):
        # Strategia F1: Neutral 45-55, Greed 56-74
        self.assertEqual(zone_from_score(45.0), "neutral")
        self.assertEqual(zone_from_score(55.0), "neutral")
        self.assertEqual(zone_from_score(56.0), "greed")

    def test_strategy_boundary_fear_neutral(self):
        # Strategia F1: Fear 25-44, Neutral 45-55
        self.assertEqual(zone_from_score(44.0), "fear")
        self.assertEqual(zone_from_score(45.0), "neutral")


class TestParseScore(unittest.TestCase):
    def test_returns_score_and_zone(self):
        payload = {"fear_and_greed": {"score": 42.5, "rating": "fear"}}
        result = parse_score(payload)
        self.assertEqual(result, {"score": 42.5, "zone": "fear"})

    def test_derives_zone_when_rating_missing(self):
        payload = {"fear_and_greed": {"score": 80.0}}
        result = parse_score(payload)
        self.assertEqual(result["score"], 80.0)
        self.assertEqual(result["zone"], "extreme greed")

    def test_raises_when_score_missing(self):
        with self.assertRaises(KeyError):
            parse_score({"fear_and_greed": {}})


class TestParseComponents(unittest.TestCase):
    _PAYLOAD = {
        "market_momentum_sp500": {"score": 74.6, "rating": "greed"},
        "stock_price_strength": {"score": 28.6, "rating": "fear"},
        "stock_price_breadth": {"score": 57.8, "rating": "greed"},
        "put_call_options": {"score": 66.4, "rating": "greed"},
        "market_volatility_vix": {"score": 50.0, "rating": "neutral"},
        "junk_bond_demand": {"score": 98.6, "rating": "extreme greed"},
        "safe_haven_demand": {"score": 78.8, "rating": "extreme greed"},
    }

    def test_parses_all_seven_components(self):
        result = parse_components(self._PAYLOAD)
        self.assertEqual(len(result), 7)
        self.assertEqual(result["market_momentum"], {"score": 74.6, "rating": "greed"})
        self.assertEqual(result["stock_price_strength"], {"score": 28.6, "rating": "fear"})
        self.assertEqual(result["stock_price_breadth"], {"score": 57.8, "rating": "greed"})
        self.assertEqual(result["put_call_options"], {"score": 66.4, "rating": "greed"})
        self.assertEqual(result["market_volatility"], {"score": 50.0, "rating": "neutral"})
        self.assertEqual(result["junk_bond_demand"], {"score": 98.6, "rating": "extreme greed"})
        self.assertEqual(result["safe_haven_demand"], {"score": 78.8, "rating": "extreme greed"})

    def test_skips_missing_component(self):
        payload = dict(self._PAYLOAD)
        del payload["market_volatility_vix"]
        result = parse_components(payload)
        self.assertEqual(len(result), 6)
        self.assertNotIn("market_volatility", result)

    def test_skips_malformed_component(self):
        payload = dict(self._PAYLOAD)
        payload["junk_bond_demand"] = {"score": "not-a-number"}  # score non float
        result = parse_components(payload)
        self.assertNotIn("junk_bond_demand", result)
        self.assertIn("market_momentum", result)

    def test_returns_empty_when_no_valid_components(self):
        self.assertEqual(parse_components({}), {})


class TestParseCnn(unittest.TestCase):
    def test_parses_score_and_zone(self):
        body = '{"fear_and_greed": {"score": 66.7, "rating": "greed"}}'
        result = parse_cnn(body)
        self.assertEqual(result, {"score": 66.7, "zone": "greed"})

    def test_derives_zone_when_rating_missing(self):
        body = '{"fear_and_greed": {"score": 80.0}}'
        result = parse_cnn(body)
        self.assertEqual(result["score"], 80.0)
        self.assertEqual(result["zone"], "extreme greed")

    def test_raises_on_malformed_json(self):
        with self.assertRaises(ValueError):
            parse_cnn("not json")


class TestParseCnnComponents(unittest.TestCase):
    _BODY = json.dumps({
        "fear_and_greed": {"score": 66.7, "rating": "greed"},
        "market_momentum_sp500": {"score": 74.6, "rating": "greed"},
        "stock_price_strength": {"score": 28.6, "rating": "fear"},
        "stock_price_breadth": {"score": 57.8, "rating": "greed"},
        "put_call_options": {"score": 66.4, "rating": "greed"},
        "market_volatility_vix": {"score": 50.0, "rating": "neutral"},
        "junk_bond_demand": {"score": 98.6, "rating": "extreme greed"},
        "safe_haven_demand": {"score": 78.8, "rating": "extreme greed"},
    })

    def test_parse_cnn_includes_components(self):
        result = parse_cnn(self._BODY)
        self.assertEqual(result["score"], 66.7)
        self.assertEqual(result["zone"], "greed")
        self.assertEqual(len(result["fgi_components"]), 7)
        self.assertEqual(result["fgi_components"]["market_momentum"], {"score": 74.6, "rating": "greed"})

    def test_parse_cnn_omits_components_when_absent(self):
        body = '{"fear_and_greed": {"score": 66.7, "rating": "greed"}}'
        result = parse_cnn(body)
        self.assertNotIn("fgi_components", result)


class TestParseFeargreedmeter(unittest.TestCase):
    def test_parses_title(self):
        # title: "Fear and Greed Index: 67 (Greed) | Stock Market Sentiment"
        html = (
            "<html><head><title>Fear and Greed Index: 67 (Greed) | "
            "Stock Market Sentiment</title></head></html>"
        )
        data = parse_feargreedmeter(html)
        self.assertEqual(data["score"], 67)
        self.assertEqual(data["zone"], "greed")

    def test_raises_when_title_missing(self):
        with self.assertRaises(ValueError):
            parse_feargreedmeter("<html><body>no title</body></html>")

    def test_raises_without_stock_market_marker(self):
        # Il sito pubblica anche un FGI crypto: senza il marker "Stock Market"
        # il parser deve rifiutare per evitare deriva semantica.
        html = (
            "<html><head><title>Fear and Greed Index: 29 (Fear) | "
            "Crypto Market Sentiment</title></head></html>"
        )
        with self.assertRaises(ValueError):
            parse_feargreedmeter(html)


class TestParseFeargreedindex(unittest.TestCase):
    def test_parses_json_body(self):
        body = '{"value":71,"label":"Greed","source":"stock"}'
        data = parse_feargreedindex(body)
        self.assertEqual(data["score"], 71)
        self.assertEqual(data["zone"], "greed")

    def test_uses_base_value_when_present(self):
        # value include i voti community (distorsione), baseValue è l'indice
        # oggettivo → deve vincere baseValue.
        body = (
            '{"value":71,"baseValue":74,"label":"Greed","source":"stock",'
            '"votes":[{"id":"fear","count":1},{"id":"extreme-greed","count":1}]}'
        )
        data = parse_feargreedindex(body)
        self.assertEqual(data["score"], 74)
        self.assertEqual(data["zone"], "greed")

    def test_raises_on_malformed_json(self):
        with self.assertRaises(ValueError):
            parse_feargreedindex("not json")

    def test_raises_when_no_score_fields(self):
        with self.assertRaises(KeyError):
            parse_feargreedindex('{"label":"Greed"}')


class TestParseHtml(unittest.TestCase):
    def test_parses_gauge_value(self):
        html = (
            '<span class="market-fng-gauge__dial-number-value">63.5</span>'
        )
        result = parse_html(html)
        self.assertEqual(result["score"], 63.5)
        self.assertEqual(result["zone"], "greed")

    def test_raises_when_gauge_missing(self):
        with self.assertRaises(ValueError):
            parse_html("<html><body>no gauge</body></html>")


class TestBuildResult(unittest.TestCase):
    def test_builds_file_json_shape(self):
        result = build_result(42.0, "fear", "2026-08-07T08:00:00+00:00")
        self.assertEqual(result["score"], 42.0)
        self.assertEqual(result["zone"], "fear")
        self.assertEqual(result["frequency"], "daily")
        self.assertEqual(result["stale_after_hours"], 24)
        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["fetched_at"], "2026-08-07T08:00:00+00:00")


class TestBuildResultComponents(unittest.TestCase):
    def test_includes_components_when_given(self):
        comps = {"market_momentum": {"score": 74.6, "rating": "greed"}}
        result = build_result(66.7, "greed", "2026-08-07T08:00:00+00:00", fgi_components=comps)
        self.assertEqual(result["fgi_components"], comps)

    def test_omits_components_when_none(self):
        result = build_result(66.7, "greed", "2026-08-07T08:00:00+00:00")
        self.assertNotIn("fgi_components", result)


class TestRun(unittest.TestCase):
    def test_run_marks_source_cnn(self):
        # with the CNN responding, source = "cnn"
        body = '{"fear_and_greed": {"score": 66.7, "rating": "greed"}}'
        with mock.patch(
            "scrapers.fgi_scraper.fetch_first_success",
            return_value=(body, "cnn"),
        ):
            result = run()
        self.assertEqual(result["source"], "cnn")
        self.assertEqual(result["score"], 66.7)
        self.assertEqual(result["zone"], "greed")
        self.assertEqual(result["status"], "fresh")

    def test_run_marks_source_feargreedindex_on_fallback(self):
        body = '{"value":71,"label":"Greed","source":"stock"}'
        with mock.patch(
            "scrapers.fgi_scraper.fetch_first_success",
            return_value=(body, "feargreedindex"),
        ):
            result = run()
        self.assertEqual(result["source"], "feargreedindex")
        self.assertEqual(result["score"], 71)
        self.assertEqual(result["zone"], "greed")
        self.assertEqual(result["status"], "fresh")

    def test_run_marks_source_feargreedmeter_on_fallback(self):
        body = (
            "<html><head><title>Fear and Greed Index: 67 (Greed) | "
            "Stock Market Sentiment</title></head></html>"
        )
        with mock.patch(
            "scrapers.fgi_scraper.fetch_first_success",
            return_value=(body, "feargreedmeter"),
        ):
            result = run()
        self.assertEqual(result["source"], "feargreedmeter")
        self.assertEqual(result["score"], 67)
        self.assertEqual(result["zone"], "greed")
        self.assertEqual(result["status"], "fresh")

    def test_chain_skips_source_with_unparseable_body(self):
        # CNN risponde 200 con body inatteso (block page) → il validatore la
        # rifiuta e la catena deve passare alla fonte successiva.
        cnn_body = "<html><body>Just a moment...</body></html>"  # non-CNN JSON
        meter_body = (
            "<html><head><title>Fear and Greed Index: 67 (Greed) | "
            "Stock Market Sentiment</title></head></html>"
        )
        with mock.patch(
            "scrapers.fgi_scraper.fetch_first_success",
            return_value=(meter_body, "feargreedmeter"),
        ) as mock_fetch:
            result = run()
        # Il validatore deve essere stato passato a fetch_first_success
        kwargs = mock_fetch.call_args.kwargs
        self.assertIn("validate", kwargs)
        self.assertTrue(callable(kwargs["validate"]))
        # Il validatore rifiuta il body CNN non parsabile
        from scrapers.fgi_scraper import parse_cnn
        self.assertFalse(kwargs["validate"]("cnn", cnn_body))
        # Il validatore accetta il body meter
        self.assertTrue(kwargs["validate"]("feargreedmeter", meter_body))
        # Il validatore rifiuta un body meter senza marker "Stock Market"
        # (ipotetico title crypto: 29 Fear | Crypto Market Sentiment)
        crypto_body = (
            "<html><head><title>Fear and Greed Index: 29 (Fear) | "
            "Crypto Market Sentiment</title></head></html>"
        )
        self.assertFalse(kwargs["validate"]("feargreedmeter", crypto_body))
        self.assertEqual(result["source"], "feargreedmeter")


class TestRunComponents(unittest.TestCase):
    def test_run_cnn_includes_components(self):
        body = json.dumps({
            "fear_and_greed": {"score": 66.7, "rating": "greed"},
            "market_momentum_sp500": {"score": 74.6, "rating": "greed"},
        })
        with mock.patch(
            "scrapers.fgi_scraper.fetch_first_success",
            return_value=(body, "cnn"),
        ):
            result = run()
        self.assertEqual(result["source"], "cnn")
        self.assertIn("fgi_components", result)
        self.assertEqual(result["fgi_components"]["market_momentum"], {"score": 74.6, "rating": "greed"})

    def test_run_fallback_omits_components(self):
        body = '{"value":71,"label":"Greed","source":"stock"}'
        with mock.patch(
            "scrapers.fgi_scraper.fetch_first_success",
            return_value=(body, "feargreedindex"),
        ):
            result = run()
        self.assertEqual(result["source"], "feargreedindex")
        self.assertNotIn("fgi_components", result)


if __name__ == "__main__":
    unittest.main()
