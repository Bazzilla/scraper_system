"""Unit tests for the portfolio HTML page generator."""

from __future__ import annotations

import unittest

from portfolio_page import render_portfolio_page


class TestPortfolioPage(unittest.TestCase):
    def test_page_has_nav(self):
        html = render_portfolio_page()
        self.assertIn('class="page-nav"', html)
        self.assertIn('href="/report.html"', html)
        self.assertIn('href="/portfolio.html"', html)
        self.assertIn('class="nav-link active">💼 Portfolio</a>', html)

    def test_page_has_summary_section(self):
        html = render_portfolio_page()
        self.assertIn('id="summary-card"', html)
        self.assertIn('id="s-count"', html)
        self.assertIn('id="s-value"', html)
        self.assertIn('id="s-cost"', html)
        self.assertIn('id="s-unrealized"', html)
        self.assertIn('id="s-realized"', html)
        self.assertIn('id="s-total"', html)

    def test_page_has_positions_table(self):
        html = render_portfolio_page()
        self.assertIn('id="positions-tbody"', html)
        self.assertIn('id="positions-empty"', html)
        self.assertIn('Prezzo medio', html)

    def test_page_has_transactions_table(self):
        html = render_portfolio_page()
        self.assertIn('id="transactions-tbody"', html)
        self.assertIn('id="transactions-empty"', html)
        self.assertIn('Modifica', html) or self.assertIn('modifica', html)

    def test_page_has_transaction_form(self):
        html = render_portfolio_page()
        self.assertIn('id="f-date"', html)
        self.assertIn('id="f-ticker"', html)
        self.assertIn('id="f-action"', html)
        self.assertIn('id="f-qty"', html)
        self.assertIn('id="f-price"', html)
        self.assertIn('id="f-comm"', html)
        self.assertIn('id="f-note"', html)
        self.assertIn('id="f-submit"', html)

    def test_page_has_api_calls(self):
        html = render_portfolio_page()
        self.assertIn('/api/positions', html)
        self.assertIn('/api/transactions', html)
        self.assertIn('/api/portfolio/evaluate', html)

    def test_page_has_sell_signals_section(self):
        html = render_portfolio_page()
        self.assertIn('id="sell-body"', html)
        self.assertIn('id="sell-list"', html)
        self.assertIn('id="sell-empty"', html)
        self.assertIn('Segnali SELL', html)

    def test_page_has_sell_css(self):
        html = render_portfolio_page()
        self.assertIn('sell-badge', html)
        self.assertIn('sell-MANTIENI', html)
        self.assertIn('sell-PRENDI', html)
        self.assertIn('sell-RIDUCI', html)
        self.assertIn('sell-ATTENZIONE', html)

    def test_page_has_sell_js_functions(self):
        html = render_portfolio_page()
        self.assertIn('loadSellSignals', html)
        self.assertIn('renderSellSignals', html)

    def test_no_client_side_calculations(self):
        """The page must NOT contain any P/L or average-cost calculation logic."""
        html = render_portfolio_page()
        # No average cost calculation formula
        self.assertNotIn('average_cost', html)
        self.assertNotIn('averageEntry', html)
        # No P/L calculation formulas (the page only reads values from API)
        self.assertNotIn('total_cost *', html)
        self.assertNotIn('* quantity', html)
        self.assertNotIn('/ total_cost', html)
        # unrealized_pnl_usd / unrealized_pnl_pct are API field names
        # (displayed, not calculated) — that's fine

    def test_page_is_valid_html(self):
        html = render_portfolio_page()
        self.assertIn('<!DOCTYPE html>', html)
        self.assertIn('<html', html)
        self.assertIn('</html>', html)
        self.assertIn('<script>', html)
        self.assertIn('</script>', html)


if __name__ == "__main__":
    unittest.main()
