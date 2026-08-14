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

    def test_entry_must_be_mapping(self):
        with self.assertRaises(ValueError):
            validate_config(_config_with_tickers({"semiconductors": ["AMAT"]}))

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


if __name__ == "__main__":
    unittest.main()
