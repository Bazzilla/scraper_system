"""Unit tests for the manual overrides entry page generator."""

from __future__ import annotations

import unittest

from overrides_page import render_overrides_page


class TestRenderOverridesPage(unittest.TestCase):
    def test_renders_header_with_links_and_toggle(self):
        html = render_overrides_page({})
        self.assertIn("Immissione manuale", html)
        # Menù di navigazione condiviso (link a tutte le pagine)
        self.assertIn('class="page-nav"', html)
        self.assertIn('href="/report.html"', html)
        self.assertIn('href="/tickers.html"', html)
        self.assertIn("theme-toggle", html)

    def test_renders_card_per_indicator(self):
        overrides = {
            "naaim": {"exposure": 79.70, "stale_after_hours": 168, "entered_by": "user"},
            "vix_term_structure": {"m1": 15.6, "m2": 17.9},
        }
        html = render_overrides_page(overrides)
        self.assertIn("NAAIM", html)
        self.assertIn("VIX Term Structure", html)
        # str(79.70) == "79.7" (float normalizzato)
        self.assertIn("79.7", html)
        self.assertIn("15.6", html)

    def test_renders_enabled_checkbox(self):
        overrides = {"naaim": {"exposure": 79.70, "enabled": False}}
        html = render_overrides_page(overrides)
        self.assertIn('name="enabled"', html)
        # enabled=False → la checkbox della card naaim NON è checked.
        # Scope sulla card naaim: la prima name="enabled" è della card aaii
        # (rendered prima, enabled=True di default).
        card = html.split('data-key="naaim"')[1]
        checkbox = card.split('name="enabled"')[1][:200]
        self.assertNotIn("checked", checkbox)

    def test_renders_checked_when_enabled(self):
        overrides = {"naaim": {"exposure": 79.70, "enabled": True}}
        html = render_overrides_page(overrides)
        card = html.split('data-key="naaim"')[1]
        checkbox = card.split('name="enabled"')[1][:200]
        self.assertIn("checked", checkbox)
