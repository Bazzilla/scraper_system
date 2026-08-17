"""Unit tests for the shared indicator descriptor module (indicator_fields)."""

from __future__ import annotations

import unittest

from indicator_fields import INDICATOR_FIELDS, SUPPORTED_KEYS

EXPECTED_KEYS = {"aaii", "fgi", "naaim", "vix_term_structure", "pct_sma"}

DESCRIPTOR_KEYS = {"label", "badge", "frequency", "fields", "required"}


class TestSupportedKeys(unittest.TestCase):
    def test_supported_keys_has_exactly_five_expected(self):
        self.assertEqual(SUPPORTED_KEYS, frozenset(EXPECTED_KEYS))

    def test_supported_keys_matches_descriptor_keys(self):
        self.assertEqual(SUPPORTED_KEYS, frozenset(INDICATOR_FIELDS))


class TestDescriptors(unittest.TestCase):
    def test_every_descriptor_has_required_keys(self):
        for key in EXPECTED_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, INDICATOR_FIELDS)
                descriptor = INDICATOR_FIELDS[key]
                for field in DESCRIPTOR_KEYS:
                    self.assertIn(field, descriptor, f"{key} missing {field!r}")

    def test_every_required_field_has_a_field_spec(self):
        for key in EXPECTED_KEYS:
            with self.subTest(key=key):
                descriptor = INDICATOR_FIELDS[key]
                for field in descriptor["required"]:
                    self.assertIn(field, descriptor["fields"])

    def test_every_field_spec_has_label_type_step(self):
        for key in EXPECTED_KEYS:
            with self.subTest(key=key):
                for field, spec in INDICATOR_FIELDS[key]["fields"].items():
                    self.assertIn("label", spec, f"{key}.{field} missing label")
                    self.assertIn("type", spec, f"{key}.{field} missing type")
                    self.assertIn("step", spec, f"{key}.{field} missing step")

    def test_badge_is_valid(self):
        for key in EXPECTED_KEYS:
            with self.subTest(key=key):
                self.assertIn(INDICATOR_FIELDS[key]["badge"], {"manual", "fallback"})


if __name__ == "__main__":
    unittest.main()
