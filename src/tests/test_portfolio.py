"""Unit tests for the portfolio engine (position calculation)."""

from __future__ import annotations

import unittest

from portfolio import PortfolioError, PortfolioResult, Position, calculate_positions


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tx(
    ticker: str,
    action: str,
    qty: float,
    price: float,
    commission: float = 0.0,
    date: str = "2026-08-27",
    note: str | None = None,
) -> dict:
    return {
        "trade_date": date,
        "ticker": ticker,
        "action": action,
        "quantity": qty,
        "price_usd": price,
        "commission_usd": commission,
        "note": note,
    }


# ── Single BUY ───────────────────────────────────────────────────────────────

class TestSingleBuy(unittest.TestCase):
    def test_single_buy(self):
        txs = [_tx("NVDA", "BUY", 10, 125.0, commission=1.0)]
        result = calculate_positions(txs)
        self.assertEqual(len(result.positions), 1)
        pos = result.positions["NVDA"]
        self.assertEqual(pos.quantity, 10)
        # total_cost = 10*125 + 1 = 1251, avg = 1251/10 = 125.1
        self.assertAlmostEqual(pos.average_entry_price, 125.1)
        self.assertAlmostEqual(pos.total_cost, 1251.0)

    def test_single_buy_no_commission(self):
        txs = [_tx("NVDA", "BUY", 10, 100.0)]
        result = calculate_positions(txs)
        pos = result.positions["NVDA"]
        self.assertEqual(pos.quantity, 10)
        self.assertAlmostEqual(pos.average_entry_price, 100.0)
        self.assertAlmostEqual(pos.total_cost, 1000.0)


# ── Two BUYs same ticker ────────────────────────────────────────────────────

class TestTwoBuys(unittest.TestCase):
    def test_two_buys_same_ticker(self):
        txs = [
            _tx("NVDA", "BUY", 10, 100.0, date="2026-08-01"),
            _tx("NVDA", "BUY", 10, 150.0, date="2026-08-15"),
        ]
        result = calculate_positions(txs)
        pos = result.positions["NVDA"]
        self.assertEqual(pos.quantity, 20)
        # total cost = 1000 + 1500 = 2500, avg = 125
        self.assertAlmostEqual(pos.total_cost, 2500.0)
        self.assertAlmostEqual(pos.average_entry_price, 125.0)


# ── BUY + partial SELL ──────────────────────────────────────────────────────

class TestPartialSell(unittest.TestCase):
    def test_partial_sell(self):
        txs = [
            _tx("NVDA", "BUY", 10, 100.0, date="2026-08-01"),
            _tx("NVDA", "SELL", 5, 120.0, date="2026-08-15"),
        ]
        result = calculate_positions(txs)
        pos = result.positions["NVDA"]
        self.assertEqual(pos.quantity, 5)
        self.assertAlmostEqual(pos.average_entry_price, 100.0)
        self.assertAlmostEqual(pos.total_cost, 500.0)
        # realized P/L: sold 5 @ 120 = 600, cost basis = 500, pnl = 100
        self.assertAlmostEqual(pos.realized_pnl, 100.0)
        self.assertAlmostEqual(result.realized_pnl_by_ticker["NVDA"], 100.0)


# ── BUY + full SELL ─────────────────────────────────────────────────────────

class TestFullSell(unittest.TestCase):
    def test_full_sell_closes_position(self):
        txs = [
            _tx("NVDA", "BUY", 10, 100.0, date="2026-08-01"),
            _tx("NVDA", "SELL", 10, 120.0, date="2026-08-15"),
        ]
        result = calculate_positions(txs)
        self.assertEqual(len(result.positions), 0)
        self.assertEqual(len(result.realized_pnl_by_ticker), 1)
        self.assertAlmostEqual(result.realized_pnl_by_ticker["NVDA"], 200.0)


# ── Rebuy after full sell ───────────────────────────────────────────────────

class TestRebuy(unittest.TestCase):
    def test_rebuy_after_full_sell(self):
        txs = [
            _tx("NVDA", "BUY", 10, 100.0, date="2026-08-01"),
            _tx("NVDA", "SELL", 10, 120.0, date="2026-08-10"),
            _tx("NVDA", "BUY", 5, 130.0, date="2026-08-15"),
        ]
        result = calculate_positions(txs)
        pos = result.positions["NVDA"]
        self.assertEqual(pos.quantity, 5)
        self.assertAlmostEqual(pos.average_entry_price, 130.0)
        self.assertAlmostEqual(pos.total_cost, 650.0)
        # realized from first trade cycle: 200
        self.assertAlmostEqual(result.realized_pnl_by_ticker["NVDA"], 200.0)


# ── SELL exceeds position ───────────────────────────────────────────────────

class TestSellExceeds(unittest.TestCase):
    def test_sell_exceeds_raises(self):
        txs = [
            _tx("NVDA", "BUY", 10, 100.0),
            _tx("NVDA", "SELL", 15, 120.0),
        ]
        with self.assertRaises(PortfolioError) as ctx:
            calculate_positions(txs)
        self.assertIn("exceeds", str(ctx.exception))

    def test_sell_on_no_position_raises(self):
        txs = [_tx("NVDA", "SELL", 5, 120.0)]
        with self.assertRaises(PortfolioError):
            calculate_positions(txs)


# ── Commissions ──────────────────────────────────────────────────────────────

class TestCommissions(unittest.TestCase):
    def test_buy_commission_increases_cost(self):
        txs = [_tx("NVDA", "BUY", 10, 100.0, commission=10.0)]
        result = calculate_positions(txs)
        pos = result.positions["NVDA"]
        self.assertAlmostEqual(pos.total_cost, 1010.0)
        self.assertAlmostEqual(pos.average_entry_price, 101.0)

    def test_sell_commission_reduces_proceeds(self):
        txs = [
            _tx("NVDA", "BUY", 10, 100.0, date="2026-08-01"),
            _tx("NVDA", "SELL", 5, 120.0, commission=5.0, date="2026-08-15"),
        ]
        result = calculate_positions(txs)
        # proceeds = 5*120 - 5 = 595, cost basis = 500, realized = 95
        self.assertAlmostEqual(result.realized_pnl_by_ticker["NVDA"], 95.0)


# ── Unrealized P/L with prices ──────────────────────────────────────────────

class TestUnrealizedPnL(unittest.TestCase):
    def test_with_price(self):
        txs = [_tx("NVDA", "BUY", 10, 100.0)]
        result = calculate_positions(txs, prices={"NVDA": 150.0})
        pos = result.positions["NVDA"]
        self.assertEqual(pos.market_price, 150.0)
        self.assertIsNotNone(pos.market_value)
        self.assertIsNotNone(pos.unrealized_pnl)
        self.assertIsNotNone(pos.unrealized_pnl_pct)
        assert pos.market_value is not None
        assert pos.unrealized_pnl is not None
        assert pos.unrealized_pnl_pct is not None
        self.assertAlmostEqual(pos.market_value, 1500.0)
        self.assertAlmostEqual(pos.unrealized_pnl, 500.0)
        self.assertAlmostEqual(pos.unrealized_pnl_pct, 50.0)

    def test_without_price(self):
        txs = [_tx("NVDA", "BUY", 10, 100.0)]
        result = calculate_positions(txs)
        pos = result.positions["NVDA"]
        self.assertIsNone(pos.market_price)
        self.assertIsNone(pos.market_value)
        self.assertIsNone(pos.unrealized_pnl)
        self.assertIsNone(pos.unrealized_pnl_pct)

    def test_total_pnl_with_price(self):
        txs = [
            _tx("NVDA", "BUY", 10, 100.0, date="2026-08-01"),
            _tx("NVDA", "SELL", 5, 120.0, date="2026-08-10"),
        ]
        result = calculate_positions(txs, prices={"NVDA": 140.0})
        pos = result.positions["NVDA"]
        # realized = 100, unrealized = 5*140 - 500 = 200
        self.assertIsNotNone(pos.total_pnl)
        assert pos.total_pnl is not None
        self.assertAlmostEqual(pos.total_pnl, 300.0)


# ── Multiple tickers ────────────────────────────────────────────────────────

class TestMultipleTickers(unittest.TestCase):
    def test_independent_tickers(self):
        txs = [
            _tx("NVDA", "BUY", 10, 100.0, date="2026-08-01"),
            _tx("LMT", "BUY", 5, 400.0, date="2026-08-02"),
            _tx("NVDA", "SELL", 5, 120.0, date="2026-08-10"),
        ]
        result = calculate_positions(txs)
        self.assertEqual(len(result.positions), 2)
        self.assertEqual(result.positions["NVDA"].quantity, 5)
        self.assertEqual(result.positions["LMT"].quantity, 5)
        # realized only for NVDA
        self.assertAlmostEqual(result.realized_pnl_by_ticker["NVDA"], 100.0)
        self.assertNotIn("LMT", result.realized_pnl_by_ticker)


# ── Multiple sells accumulate realized P/L ───────────────────────────────────

class TestRealizedAccumulator(unittest.TestCase):
    def test_two_sells_accumulate(self):
        txs = [
            _tx("NVDA", "BUY", 20, 100.0, date="2026-08-01"),
            _tx("NVDA", "SELL", 5, 120.0, date="2026-08-10"),
            _tx("NVDA", "SELL", 5, 140.0, date="2026-08-15"),
        ]
        result = calculate_positions(txs)
        # sell 1: proceeds=600, cost=500, pnl=100
        # sell 2: proceeds=700, cost=500, pnl=200
        self.assertAlmostEqual(result.realized_pnl_by_ticker["NVDA"], 300.0)
        pos = result.positions["NVDA"]
        self.assertEqual(pos.quantity, 10)

    def test_accumulator_persists_after_recalc(self):
        """Realized P/L does not reset when recalculating from transactions."""
        txs = [
            _tx("NVDA", "BUY", 20, 100.0, date="2026-08-01"),
            _tx("NVDA", "SELL", 5, 120.0, date="2026-08-10"),
        ]
        r1 = calculate_positions(txs)
        r2 = calculate_positions(txs)  # same input, recalculated
        self.assertAlmostEqual(
            r1.realized_pnl_by_ticker["NVDA"],
            r2.realized_pnl_by_ticker["NVDA"],
        )

    def test_rebuy_after_sell_accumulates(self):
        txs = [
            _tx("NVDA", "BUY", 10, 100.0, date="2026-08-01"),
            _tx("NVDA", "SELL", 10, 130.0, date="2026-08-10"),
            _tx("NVDA", "BUY", 10, 110.0, date="2026-08-15"),
            _tx("NVDA", "SELL", 10, 150.0, date="2026-08-20"),
        ]
        result = calculate_positions(txs)
        # sell 1: 1300-1000=300, sell 2: 1500-1100=400
        self.assertAlmostEqual(result.realized_pnl_by_ticker["NVDA"], 700.0)
        self.assertEqual(len(result.positions), 0)


# ── Average cost accuracy ───────────────────────────────────────────────────

class TestAverageCost(unittest.TestCase):
    def test_average_cost_unaffected_by_sell(self):
        txs = [
            _tx("NVDA", "BUY", 10, 100.0, date="2026-08-01"),
            _tx("NVDA", "BUY", 10, 150.0, date="2026-08-05"),
            _tx("NVDA", "SELL", 5, 200.0, date="2026-08-10"),
        ]
        result = calculate_positions(txs)
        pos = result.positions["NVDA"]
        # avg = (1000+1500)/20 = 125 — unchanged after sell
        self.assertAlmostEqual(pos.average_entry_price, 125.0)
        self.assertEqual(pos.quantity, 15)


# ── Empty / edge cases ──────────────────────────────────────────────────────

class TestEdgeCases(unittest.TestCase):
    def test_empty_transactions(self):
        result = calculate_positions([])
        self.assertEqual(len(result.positions), 0)
        self.assertEqual(len(result.realized_pnl_by_ticker), 0)

    def test_only_buys_no_realized(self):
        txs = [_tx("NVDA", "BUY", 10, 100.0)]
        result = calculate_positions(txs)
        self.assertEqual(len(result.realized_pnl_by_ticker), 0)

    def test_zero_commission(self):
        txs = [_tx("NVDA", "BUY", 10, 100.0, commission=0.0)]
        result = calculate_positions(txs)
        self.assertAlmostEqual(result.positions["NVDA"].total_cost, 1000.0)


if __name__ == "__main__":
    unittest.main()
