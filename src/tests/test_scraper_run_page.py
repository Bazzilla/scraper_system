"""Tests for the scraper-run page."""

import unittest

from scraper_run_page import render_scraper_run_page


class TestScraperRunPage(unittest.TestCase):
    def test_render_contains_title(self):
        html = render_scraper_run_page()
        self.assertIn("Esecuzione scraping", html)

    def test_render_has_nav_links(self):
        html = render_scraper_run_page()
        self.assertIn("/report.html", html)
        self.assertIn("/overrides.html", html)
        self.assertIn("/tickers.html", html)
        self.assertIn("/scraper-run.html", html)

    def test_render_has_active_nav(self):
        html = render_scraper_run_page()
        self.assertIn('class="nav-link active"', html)

    def test_render_has_three_modes(self):
        html = render_scraper_run_page()
        self.assertIn('value="full"', html)
        self.assertIn('value="report_only"', html)
        self.assertIn('value="override_only"', html)

    def test_render_has_run_button(self):
        html = render_scraper_run_page()
        self.assertIn("run-btn", html)
        self.assertIn("▶ Avvia", html)

    def test_render_has_output_area(self):
        html = render_scraper_run_page()
        self.assertIn('id="output"', html)

    def test_render_uses_event_source(self):
        html = render_scraper_run_page()
        self.assertIn("EventSource", html)
        self.assertIn("/api/scraper-run", html)

    def test_render_has_mode_descriptions(self):
        html = render_scraper_run_page()
        self.assertIn("Pipeline completa", html)
        self.assertIn("Solo report", html)
        self.assertIn("Solo override", html)


if __name__ == "__main__":
    unittest.main()
