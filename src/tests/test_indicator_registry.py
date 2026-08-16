"""Unit tests for the indicator registry (strategy coverage matrix)."""

from __future__ import annotations

import unittest

from indicator_registry import (
    STATUS_IMPLEMENTED,
    STATUS_MANUAL_SUPPORTED,
    STATUS_MISSING,
    STATUS_PROXY,
    build_availability,
    coverage_for,
    load_and_summarize,
    load_registry,
    normalize_registry,
    summarize,
)


class TestLoadAndNormalize(unittest.TestCase):
    def test_loads_default_registry(self):
        registry = load_registry()
        self.assertIn("indicators", registry)
        self.assertIn("fgi", registry["indicators"])

    def test_normalize_fills_defaults(self):
        raw = {"indicators": {"x": {"implementation_status": "missing"}}}
        normalized = normalize_registry(raw)
        entry = normalized["indicators"]["x"]
        self.assertEqual(entry["implementation_status"], "missing")
        self.assertFalse(entry["semantic_coherent"])
        self.assertEqual(entry["fallbacks"], [])
        self.assertIsNone(entry["output_key"])
        self.assertFalse(entry["coverage"])

    def test_normalize_accepts_legacy_status_field(self):
        # Retrocompatibilità: il vecchio campo `status` viene mappato a
        # implementation_status.
        raw = {"indicators": {"x": {"status": "implemented"}}}
        normalized = normalize_registry(raw)
        self.assertEqual(
            normalized["indicators"]["x"]["implementation_status"], "implemented"
        )

    def test_invalid_status_raises(self):
        raw = {"indicators": {"x": {"implementation_status": "bogus"}}}
        with self.assertRaises(ValueError):
            normalize_registry(raw)


class TestCoverage(unittest.TestCase):
    def test_coverage_is_static_from_registry(self):
        # coverage dipende dalle specifiche strategiche, non dal runtime.
        registry = normalize_registry(
            {
                "indicators": {
                    "fgi": {"coverage": True, "implementation_status": "implemented"},
                    "naaim": {"coverage": True, "implementation_status": "missing"},
                    "vix_spot": {"coverage": False, "implementation_status": "proxy"},
                }
            }
        )
        self.assertTrue(coverage_for(registry["indicators"]["fgi"]))
        # NAAIM previsto dalla strategia ma non implementato → coverage TRUE
        self.assertTrue(coverage_for(registry["indicators"]["naaim"]))
        # VIX spot non è un indicatore strategico → coverage FALSE
        self.assertFalse(coverage_for(registry["indicators"]["vix_spot"]))


class TestSummarize(unittest.TestCase):
    def setUp(self):
        self.registry = normalize_registry(
            {
                "indicators": {
                    "fgi": {"coverage": True, "implementation_status": "implemented",
                            "semantic_coherent": True},
                    "vix_spot": {"coverage": False, "implementation_status": "proxy",
                                 "semantic_coherent": False},
                    "nyse_nh_nl": {"coverage": True, "implementation_status": "missing"},
                    "naaim": {"coverage": True, "implementation_status": "manual_supported",
                              "semantic_coherent": True},
                }
            }
        )

    def test_default_no_proxy_accepted(self):
        result = summarize(self.registry, [])
        self.assertIn("fgi", result["summary"]["implemented"])
        self.assertIn("vix_spot", result["summary"]["proxy"])
        self.assertIn("nyse_nh_nl", result["summary"]["missing"])
        self.assertIn("naaim", result["summary"]["manual_supported"])
        self.assertTrue(result["fgi"]["usable_in_strategy_score"])
        self.assertFalse(result["vix_spot"]["usable_in_strategy_score"])
        self.assertFalse(result["nyse_nh_nl"]["usable_in_strategy_score"])

    def test_coverage_missing_strategy_indicator_stays_true(self):
        # Un indicatore strategico missing mantiene coverage=true
        result = summarize(self.registry, [])
        self.assertTrue(result["nyse_nh_nl"]["coverage"])
        self.assertEqual(result["nyse_nh_nl"]["implementation_status"], "missing")
        self.assertFalse(result["nyse_nh_nl"]["usable_in_strategy_score"])

    def test_manual_supported_usable_when_available(self):
        # NAAIM (manual_supported) disponibile → usable true
        result = summarize(
            self.registry,
            [],
            {"fgi": True, "vix_spot": True, "nyse_nh_nl": False, "naaim": True},
        )
        self.assertTrue(result["naaim"]["coverage"])
        self.assertTrue(result["naaim"]["availability"])
        self.assertTrue(result["naaim"]["usable_in_strategy_score"])

    def test_manual_supported_not_usable_when_unavailable(self):
        # NAAIM manual_supported ma nessun dato valido → non usable
        result = summarize(
            self.registry,
            [],
            {"fgi": True, "vix_spot": True, "nyse_nh_nl": False, "naaim": False},
        )
        self.assertTrue(result["naaim"]["coverage"])
        self.assertFalse(result["naaim"]["availability"])
        self.assertFalse(result["naaim"]["usable_in_strategy_score"])

    def test_proxy_accepted_becomes_usable(self):
        # VIX spot ha coverage FALSE → non usable anche se "accettato"
        result = summarize(self.registry, ["vix_spot"])
        self.assertFalse(result["vix_spot"]["usable_in_strategy_score"])
        # proxy con coverage true sarebbe usable se accettato (vedi pct_sma)
        reg2 = normalize_registry(
            {"indicators": {"pct_sma": {"coverage": True, "implementation_status": "proxy"}}}
        )
        result2 = summarize(reg2, ["pct_sma"])
        self.assertTrue(result2["pct_sma"]["usable_in_strategy_score"])

    def test_coverage_availability_usable_are_distinct(self):
        result = summarize(
            self.registry,
            [],
            {"fgi": True, "vix_spot": True, "nyse_nh_nl": False, "naaim": True},
        )
        self.assertTrue(result["fgi"]["coverage"])
        self.assertTrue(result["fgi"]["availability"])
        self.assertTrue(result["fgi"]["usable_in_strategy_score"])
        # vix_spot: coverage false, availability true, usable false
        self.assertFalse(result["vix_spot"]["coverage"])
        self.assertTrue(result["vix_spot"]["availability"])
        self.assertFalse(result["vix_spot"]["usable_in_strategy_score"])

    def test_implemented_unavailable_is_not_usable(self):
        result = summarize(
            self.registry,
            [],
            {"fgi": False, "vix_spot": False, "nyse_nh_nl": False, "naaim": False},
        )
        self.assertTrue(result["fgi"]["coverage"])
        self.assertFalse(result["fgi"]["availability"])
        self.assertFalse(result["fgi"]["usable_in_strategy_score"])

    def test_build_availability_maps_output_keys(self):
        registry = normalize_registry(
            {
                "indicators": {
                    "fgi": {"coverage": True, "implementation_status": "implemented",
                            "output_key": "fgi"},
                    "nyse_nh_nl": {"coverage": True, "implementation_status": "missing"},
                }
            }
        )
        availability = build_availability(registry, {"fgi": "fresh"})
        self.assertTrue(availability["fgi"])
        self.assertFalse(availability["nyse_nh_nl"])

        availability2 = build_availability(registry, {"fgi": "error"})
        self.assertFalse(availability2["fgi"])

    def test_real_registry_coverage_semantics(self):
        # La matrice di produzione: ogni indicatore della strategia ha
        # coverage=true (anche se missing); vix_spot (non strategico) false.
        summary = load_and_summarize()
        for key in ("fgi", "aaii", "naaim", "vix_term_structure", "pcr",
                    "nyse_nh_nl", "pct_sma", "indicators", "volume_profile",
                    "insider"):
            self.assertTrue(summary[key]["coverage"], f"{key} deve avere coverage=true")
        self.assertFalse(summary["vix_spot"]["coverage"])

        # implementation_status corretti
        for key in ("fgi", "aaii", "pcr", "indicators", "insider"):
            self.assertEqual(summary[key]["implementation_status"], STATUS_IMPLEMENTED)
        self.assertEqual(summary["vix_spot"]["implementation_status"], STATUS_PROXY)
        self.assertEqual(summary["pct_sma"]["implementation_status"], STATUS_PROXY)
        for key in ("nyse_nh_nl", "volume_profile"):
            self.assertEqual(summary[key]["implementation_status"], STATUS_MISSING)
        for key in ("naaim", "vix_term_structure"):
            self.assertEqual(summary[key]["implementation_status"], STATUS_MANUAL_SUPPORTED)

        # usable: missing mai; proxy non accettati no; vix_spot mai (coverage false)
        for key in ("nyse_nh_nl", "volume_profile"):
            self.assertFalse(summary[key]["usable_in_strategy_score"])
        self.assertFalse(summary["vix_spot"]["usable_in_strategy_score"])
        self.assertFalse(summary["pct_sma"]["usable_in_strategy_score"])


if __name__ == "__main__":
    unittest.main()
