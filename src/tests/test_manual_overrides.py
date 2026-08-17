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

VALID_VIX_TS = {
    "m1": 15.60,
    "m2": 17.90,
    "source": "manual",
    "fetched_at": "2026-08-16T17:00:00+00:00",
    "stale_after_hours": 24,
    "entered_by": "user",
    "note": "Letti manualmente da vixcentral.com",
}

VALID_PCT_SMA = {
    "pct_sma50": 45.0,
    "pct_sma200": 58.0,
    "source": "manual",
    "fetched_at": "2026-08-17T12:00:00+00:00",
    "stale_after_hours": 24,
    "entered_by": "user",
    "note": "Breadth mercato USA letta manualmente",
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

    def test_valid_vix_term_structure(self):
        cleaned = validate_entry("vix_term_structure", VALID_VIX_TS)
        self.assertEqual(cleaned["m1"], 15.6)
        self.assertEqual(cleaned["m2"], 17.9)

    def test_valid_pct_sma(self):
        cleaned = validate_entry("pct_sma", VALID_PCT_SMA)
        self.assertEqual(cleaned["pct_sma50"], 45.0)
        self.assertEqual(cleaned["pct_sma200"], 58.0)
        self.assertEqual(cleaned["source"], "manual")
        self.assertEqual(cleaned["origin"], "manual")

    def test_pct_sma_missing_field_rejected(self):
        broken = {k: v for k, v in VALID_PCT_SMA.items() if k != "pct_sma200"}
        with self.assertRaises(ValueError):
            validate_entry("pct_sma", broken)

    def test_vix_ts_missing_m2_rejected(self):
        broken = {k: v for k, v in VALID_VIX_TS.items() if k != "m2"}
        with self.assertRaises(ValueError):
            validate_entry("vix_term_structure", broken)

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

    def test_vix_ts_build_derives_structure(self):
        cleaned = validate_entry("vix_term_structure", VALID_VIX_TS)
        result = build_manual_result("vix_term_structure", cleaned, NOW)
        self.assertEqual(result["m1"], 15.6)
        self.assertEqual(result["m2"], 17.9)
        self.assertEqual(result["structure"], "contango")
        self.assertEqual(result["difference_1_2"], 2.3)
        self.assertAlmostEqual(result["contango_pct_1_2"], 14.74, places=2)
        self.assertEqual(result["source"], "manual")
        self.assertEqual(result["origin"], "manual")
        self.assertEqual(result["status"], "fresh")

    def test_pct_sma_build_manual_result(self):
        cleaned = validate_entry("pct_sma", VALID_PCT_SMA)
        result = build_manual_result("pct_sma", cleaned, NOW)
        self.assertEqual(result["pct_sma50"], 45.0)
        self.assertEqual(result["pct_sma200"], 58.0)
        self.assertEqual(result["source"], "manual")
        self.assertEqual(result["origin"], "manual")
        self.assertEqual(result["status"], "fresh")


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

    def test_persisted_manual_does_not_block_newer_override(self):
        # Regressione: un override manuale persistito nell'output (origin=manual,
        # es. da un run --override-only precedente) con status fresh NON deve
        # bloccare un override più recente dal file YAML.
        old_manual = {
            "status": "fresh",
            "origin": "manual",
            "exposure": 48.0,
            "fetched_at": "2026-08-16T12:00:00+00:00",
        }
        newer = {
            "exposure": 79.7,
            "source": "manual",
            "origin": "manual",
            "fetched_at": "2026-08-16T16:27:00+00:00",
            "stale_after_hours": 168,
            "entered_by": "user",
            "note": "Inserito manualmente da report NAAIM",
        }
        merged = apply_overrides({"naaim": old_manual}, {"naaim": newer}, now=NOW)
        self.assertEqual(merged["naaim"]["origin"], "manual")
        self.assertEqual(merged["naaim"]["exposure"], 79.7)
        self.assertEqual(
            merged["naaim"]["fetched_at"], "2026-08-16T16:27:00+00:00"
        )

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
