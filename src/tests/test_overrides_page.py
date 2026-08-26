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

    def test_renders_reference_links(self):
        html = render_overrides_page({})
        # Link fonte per la lettura manuale del dato
        self.assertIn("https://www.aaii.com/sentimentsurvey", html)
        self.assertIn("https://naaim.org/programs/naaim-exposure-index/", html)
        self.assertIn("https://volchart.io/", html)
        self.assertIn("INDEX-MMFI", html)
        self.assertIn("INDEX-MMTH", html)
        # I link si aprono in nuova scheda
        self.assertIn('target="_blank"', html)

    def test_fgi_has_no_reference_links(self):
        # Nessun URL fornito per FGI → nessun link nella sua card
        card = render_overrides_page({}).split('data-key="fgi"')[1]
        self.assertNotIn("ref-link", card.split('data-key="naaim"')[0])

    def test_card_layout_structure(self):
        html = render_overrides_page({})
        # Griglia campi con label sopra l'input
        self.assertIn('class="field-grid"', html)
        self.assertIn('class="field"', html)
        # Input decimali come text+inputmode (per accettare '.' e ',')
        self.assertIn('inputmode="decimal"', html)
        self.assertNotIn('type="number"', html)
        # Il campo Nota va sempre a capo e occupa tutta la larghezza
        self.assertIn(".field.wide { flex: 1 1 100%; }", html)
        # Footer: WRITE prima della data → date allineate a destra del tasto
        footer = html.split('class="card-footer"')[1]
        self.assertLess(footer.find(">WRITE</button>"), footer.find("Ultimo:"))
        # Struttura card: titolo → abilitato → link fonte → campi → footer
        card = html.split('data-key="naaim"')[1]
        idx_enabled = card.find('name="enabled"')
        idx_refs = card.find("ref-link")
        idx_grid = card.find('class="field-grid"')
        idx_footer = card.find('class="card-footer"')
        self.assertLess(idx_enabled, idx_refs)
        self.assertLess(idx_refs, idx_grid)
        self.assertLess(idx_grid, idx_footer)

    def test_page_has_favicon(self):
        html = render_overrides_page({})
        self.assertIn('rel="icon"', html)
        self.assertIn("data:image/svg+xml", html)
