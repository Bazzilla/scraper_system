"""Unit tests for the tickers config validation."""

from __future__ import annotations

import unittest

from typing import Any

from config_loader import validate_config


def _config_with_tickers(tickers: Any) -> dict[str, Any]:
    return {"scrapers": {"fgi": {"module": "x", "output_key": "fgi", "schedule": "daily"}}, "tickers": tickers}


class TestTickersValidation(unittest.TestCase):
    def test_valid_tickers(self):
        config = _config_with_tickers(
            {
                "semiconductors": [
                    {"symbol": "AMAT", "name": "Applied Materials"},
                    {"symbol": "LRCX", "name": "Lam Research"},
                ],
                "defense": [{"symbol": "RTX", "name": "RTX"}],
            }
        )
        result = validate_config(config)
        self.assertEqual(result["tickers"]["semiconductors"][0]["symbol"], "AMAT")

    def test_tickers_optional(self):
        config = {"scrapers": {"fgi": {"module": "x", "output_key": "fgi", "schedule": "daily"}}}
        result = validate_config(config)
        self.assertNotIn("tickers", result)

    def test_empty_tickers_mapping_ok(self):
        config = _config_with_tickers({})
        validate_config(config)

    def test_tickers_must_be_mapping(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers(["AMAT"]))

    def test_category_must_be_non_empty_list(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers({"semiconductors": []}))
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers({"semiconductors": "AMAT"}))

    def test_entry_must_be_mapping_or_string(self):
        # Legacy simple-list format: plain strings are normalized to {symbol, name}.
        result = validate_config(_config_with_tickers({"semiconductors": ["AMAT"]}))
        self.assertEqual(result["tickers"]["semiconductors"][0]["symbol"], "AMAT")
        self.assertEqual(result["tickers"]["semiconductors"][0]["name"], "AMAT")

    def test_entry_must_be_mapping_or_string_rejects_other_types(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers({"semiconductors": [123]}))

    def test_entry_missing_symbol(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers({"semiconductors": [{"name": "Applied Materials"}]}))

    def test_entry_missing_name(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers({"semiconductors": [{"symbol": "AMAT"}]}))

    def test_duplicate_symbol_across_categories(self):
        with self.assertRaises(ValueError):
            validate_config(
                _config_with_tickers(
                    {
                        "semiconductors": [{"symbol": "AMAT", "name": "A"}],
                        "defense": [{"symbol": "AMAT", "name": "B"}],
                    }
                )
            )

    def test_entry_name_must_be_string(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers(
                {"semiconductors": [{"symbol": "AMAT", "name": 123}]}))

    def test_duplicate_symbol_within_category(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers(
                {"semiconductors": [{"symbol": "AMAT", "name": "A"},
                                    {"symbol": "AMAT", "name": "B"}]}))

    def test_symbol_whitespace_only_rejected(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers(
                {"semiconductors": [{"symbol": "   ", "name": "A"}]}))

    def test_metadata_valid(self):
        config = _config_with_tickers(
            {
                "semiconductors": [
                    {
                        "symbol": "NVDA",
                        "name": "NVIDIA",
                        "quality_tier": "core",
                        "strategy_role": "compounder",
                        "buy_the_dip_validity": "high",
                        "notes": "Rischio geopolitico",
                    }
                ]
            }
        )
        result = validate_config(config)
        entry = result["tickers"]["semiconductors"][0]
        self.assertEqual(entry["quality_tier"], "core")
        self.assertEqual(entry["strategy_role"], "compounder")
        self.assertEqual(entry["buy_the_dip_validity"], "high")
        self.assertEqual(entry["notes"], "Rischio geopolitico")

    def test_metadata_optional(self):
        # Entries without metadata still validate (backward compatible).
        config = _config_with_tickers(
            {"semiconductors": [{"symbol": "AMAT", "name": "Applied Materials"}]}
        )
        result = validate_config(config)
        self.assertNotIn("quality_tier", result["tickers"]["semiconductors"][0])

    def test_invalid_quality_tier_rejected(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers(
                {"semiconductors": [{"symbol": "AMAT", "name": "A",
                                     "quality_tier": "mega"}]}))

    def test_invalid_buy_the_dip_validity_rejected(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers(
                {"semiconductors": [{"symbol": "AMAT", "name": "A",
                                     "buy_the_dip_validity": "extreme"}]}))

    def test_invalid_strategy_role_rejected(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers(
                {"semiconductors": [{"symbol": "AMAT", "name": "A",
                                     "strategy_role": "moon_shot"}]}))

    def test_notes_must_be_string(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers(
                {"semiconductors": [{"symbol": "AMAT", "name": "A",
                                     "notes": 42}]}))

    def test_normalize_tickers_legacy_list(self):
        from config_loader import normalize_tickers

        result = normalize_tickers({"semiconductors": ["AMAT", "LRCX"]})
        self.assertEqual(result["semiconductors"][0], {"symbol": "AMAT", "name": "AMAT"})
        self.assertEqual(result["semiconductors"][1], {"symbol": "LRCX", "name": "LRCX"})

    def test_normalize_tickers_enriched(self):
        from config_loader import normalize_tickers

        result = normalize_tickers(
            {"semiconductors": [{"symbol": "NVDA", "name": "NVIDIA",
                                 "quality_tier": "core"}]}
        )
        self.assertEqual(result["semiconductors"][0]["quality_tier"], "core")


if __name__ == "__main__":
    unittest.main()
