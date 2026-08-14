"""Unit tests for manual overrides (validated, traceable, fail-closed)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from manual_overrides import (
    apply_overrides,
    build_manual_result,
    build_stale_manual_result,
    is_fresh,
    validate_entry,
)

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

VALID_AAII = {
    "bullish": 37.0,
    "neutral": 25.0,
    "bearish": 38.0,
    "source": "manual",
    "fetched_at": "2026-08-14T18:20:00+00:00",
    "stale_after_hours": 168,
    "entered_by": "user",
    "note": "Inserito manualmente dal sito AAII",
}

VALID_FGI = {
    "score": 62.66,
    "zone": "greed",
    "source": "manual",
    "fetched_at": "2026-08-14T18:25:00+00:00",
    "stale_after_hours": 24,
    "entered_by": "user",
    "note": "Inserito manualmente",
}


class TestValidateEntry(unittest.TestCase):
    def test_valid_aaii(self):
        cleaned = validate_entry("aaii", VALID_AAII)
        self.assertEqual(cleaned["bullish"], 37.0)
        self.assertEqual(cleaned["source"], "manual")
        self.assertEqual(cleaned["origin"], "manual")
        self.assertEqual(cleaned["stale_after_hours"], 168)
        self.assertEqual(cleaned["entered_by"], "user")

    def test_valid_fgi(self):
        cleaned = validate_entry("fgi", VALID_FGI)
        self.assertEqual(cleaned["score"], 62.66)
        self.assertEqual(cleaned["zone"], "greed")

    def test_missing_common_field_rejected(self):
        broken = {k: v for k, v in VALID_AAII.items() if k != "fetched_at"}
        with self.assertRaises(ValueError):
            validate_entry("aaii", broken)

    def test_missing_specific_field_rejected(self):
        broken = {k: v for k, v in VALID_AAII.items() if k != "bearish"}
        with self.assertRaises(ValueError):
            validate_entry("aaii", broken)

    def test_non_numeric_value_rejected(self):
        broken = dict(VALID_AAII, bullish="high")
        with self.assertRaises(ValueError):
            validate_entry("aaii", broken)

    def test_bad_timestamp_rejected(self):
        broken = dict(VALID_AAII, fetched_at="not-a-date")
        with self.assertRaises(ValueError):
            validate_entry("aaii", broken)

    def test_non_positive_stale_window_rejected(self):
        broken = dict(VALID_AAII, stale_after_hours=0)
        with self.assertRaises(ValueError):
            validate_entry("aaii", broken)

    def test_unsupported_indicator_rejected(self):
        with self.assertRaises(ValueError):
            validate_entry("ohlcv", VALID_AAII)


class TestFreshness(unittest.TestCase):
    def test_fresh_within_window(self):
        cleaned = validate_entry("aaii", VALID_AAII)
        self.assertTrue(is_fresh(cleaned, NOW))

    def test_stale_after_window(self):
        cleaned = validate_entry("aaii", VALID_AAII)
        later = NOW + timedelta(days=8)  # 168h = 7 giorni
        self.assertFalse(is_fresh(cleaned, later))

    def test_stale_at_boundary_after(self):
        cleaned = validate_entry("fgi", VALID_FGI)
        later = NOW + timedelta(hours=25)  # 24h window
        self.assertFalse(is_fresh(cleaned, later))


class TestBuildResult(unittest.TestCase):
    def test_manual_result_is_explicitly_manual(self):
        cleaned = validate_entry("aaii", VALID_AAII)
        result = build_manual_result("aaii", cleaned, NOW)
        self.assertEqual(result["source"], "manual")
        self.assertEqual(result["origin"], "manual")
        self.assertEqual(result["status"], "fresh")
        self.assertEqual(result["entered_by"], "user")
        self.assertEqual(result["bullish"], 37.0)
        self.assertIn("note", result)

    def test_stale_result_is_stale(self):
        cleaned = validate_entry("aaii", VALID_AAII)
        result = build_stale_manual_result("aaii", cleaned, NOW)
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["origin"], "manual")


class TestApplyOverrides(unittest.TestCase):
    def _cleaned(self):
        return validate_entry("aaii", VALID_AAII)

    def test_override_used_when_scraper_fails(self):
        results = {"aaii": {"status": "error", "origin": "missing", "error": "boom"}}
        merged = apply_overrides(results, {"aaii": self._cleaned()}, now=NOW)
        self.assertEqual(merged["aaii"]["origin"], "manual")
        self.assertEqual(merged["aaii"]["status"], "fresh")
        self.assertEqual(merged["aaii"]["source"], "manual")
        self.assertEqual(merged["aaii"]["bullish"], 37.0)

    def test_override_ignored_if_malformed(self):
        # Un override malformato non viene mai applicato: il sistema logga e
        # prosegue. Qui simuliamo che il validatore l'abbia già scartato
        # (solo entry valide arrivano ad apply_overrides).
        results = {"aaii": {"status": "error", "origin": "missing", "error": "boom"}}
        merged = apply_overrides(results, {}, now=NOW)
        self.assertEqual(merged["aaii"]["status"], "error")

    def test_override_stale_results_in_stale(self):
        results = {"aaii": {"status": "error", "origin": "missing", "error": "boom"}}
        later = NOW + timedelta(days=10)
        merged = apply_overrides(results, {"aaii": self._cleaned()}, now=later)
        self.assertEqual(merged["aaii"]["status"], "stale")
        self.assertEqual(merged["aaii"]["origin"], "manual")

    def test_scraping_wins_by_default(self):
        results = {"aaii": {"status": "fresh", "origin": "scraped", "bullish": 10.0}}
        merged = apply_overrides(results, {"aaii": self._cleaned()}, now=NOW)
        self.assertEqual(merged["aaii"]["origin"], "scraped")
        self.assertEqual(merged["aaii"]["bullish"], 10.0)

    def test_force_manual_overrides_scraping(self):
        results = {"aaii": {"status": "fresh", "origin": "scraped", "bullish": 10.0}}
        merged = apply_overrides(
            results, {"aaii": self._cleaned()}, force_keys=["aaii"], now=NOW
        )
        self.assertEqual(merged["aaii"]["origin"], "manual")
        self.assertEqual(merged["aaii"]["bullish"], 37.0)

    def test_missing_override_keeps_error(self):
        # Niente scraping, niente override -> resta error (fail-closed).
        results = {"aaii": {"status": "error", "origin": "missing", "error": "boom"}}
        merged = apply_overrides(results, {}, now=NOW)
        self.assertEqual(merged["aaii"]["status"], "error")

    def test_force_manual_with_stale_keeps_scraped_fresh(self):
        # Force ma override scaduto: il dato scraped fresh resta fresh
        results = {"aaii": {"status": "fresh", "origin": "scraped", "bullish": 10.0}}
        later = NOW + timedelta(days=10)
        merged = apply_overrides(
            results, {"aaii": self._cleaned()}, force_keys=["aaii"], now=later
        )
        self.assertEqual(merged["aaii"]["origin"], "scraped")
        self.assertEqual(merged["aaii"]["status"], "fresh")


if __name__ == "__main__":
    unittest.main()
