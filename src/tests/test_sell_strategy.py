"""Tests for sell_strategy.py — SELL strategy evaluation engine."""

import unittest
from pathlib import Path

from sell_strategy import (
    SellEvaluation,
    _count_negative_signals,
    _count_overheat_signals,
    _find_ticker_data,
    _get_fgi_score,
    evaluate_all,
    evaluate_position,
    load_rules,
)

_RULES_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "sell_rules.yaml"
_RULES = load_rules(_RULES_PATH)


def _base_output(**overrides) -> dict:
    """Minimal output.json structure for testing."""
    base = {
        "fgi": {"score": 50, "zone": "Neutral"},
        "indicators": {
            "tech": {
                "NVDA": {
                    "rsi_14": 55.0,
                    "mfi_14": 50.0,
                    "sma_50": 120.0,
                    "sma_200": 115.0,
                    "obv": 1000000.0,
                    "drawdown_52w": -5.0,
                    "symbol": "NVDA",
                    "name": "NVIDIA",
                },
            },
        },
        "ohlcv": {
            "tech": {
                "NVDA": {
                    "last_close": 130.0,
                    "last_date": "2026-08-27",
                    "symbol": "NVDA",
                    "name": "NVIDIA",
                },
            },
        },
        "valuation": {
            "tech": {
                "NVDA": {
                    "upside_pct": 20.0,
                    "targetMedianPrice": 156.0,
                    "current_price": 130.0,
                },
            },
        },
    }
    base.update(overrides)
    return base


def _position(ticker="NVDA", quantity=100, avg_price=100.0, unrealized_pnl_pct=30.0):
    """Build a minimal position dict as returned by the portfolio engine."""
    return {
        "ticker": ticker,
        "quantity": quantity,
        "avg_price": avg_price,
        "last_price": avg_price * (1 + unrealized_pnl_pct / 100),
        "market_value": quantity * avg_price * (1 + unrealized_pnl_pct / 100),
        "total_cost": quantity * avg_price,
        "unrealized_pnl": quantity * avg_price * unrealized_pnl_pct / 100,
        "unrealized_pnl_pct": unrealized_pnl_pct,
        "realized_pnl": 0.0,
    }


# ── Config loading ───────────────────────────────────────────────────────────

class TestLoadRules(unittest.TestCase):
    def test_loads_actual_file(self):
        rules = load_rules(_RULES_PATH)
        self.assertIn("thresholds", rules)
        self.assertIn("signals", rules)
        self.assertEqual(rules["thresholds"]["tp1_pct"], 15)
        self.assertEqual(rules["thresholds"]["tp2_pct"], 25)
        self.assertEqual(rules["thresholds"]["tp3_pct"], 30)

    def test_missing_file_returns_empty(self):
        rules = load_rules("/nonexistent/path.yaml")
        self.assertEqual(rules, {"thresholds": {}, "signals": {}})


# ── Data extraction helpers ──────────────────────────────────────────────────

class TestFindTickerData(unittest.TestCase):
    def test_finds_indicator_data(self):
        output = _base_output()
        ind, ohlcv, val = _find_ticker_data(output, "NVDA")
        self.assertIsNotNone(ind)
        self.assertEqual(ind["rsi_14"], 55.0)
        self.assertIsNotNone(ohlcv)
        self.assertIsNotNone(val)

    def test_missing_ticker_returns_none(self):
        output = _base_output()
        ind, ohlcv, val = _find_ticker_data(output, "AAPL")
        self.assertIsNone(ind)
        self.assertIsNone(ohlcv)
        self.assertIsNone(val)

    def test_missing_category(self):
        output = _base_output(indicators={}, ohlcv={}, valuation={})
        ind, ohlcv, val = _find_ticker_data(output, "NVDA")
        self.assertIsNone(ind)
        self.assertIsNone(ohlcv)
        self.assertIsNone(val)

    def test_handles_non_dict_category(self):
        output = _base_output(indicators={"tech": "not_a_dict"})
        ind, ohlcv, val = _find_ticker_data(output, "NVDA")
        self.assertIsNone(ind)


class TestGetFgiScore(unittest.TestCase):
    def test_returns_score(self):
        self.assertEqual(_get_fgi_score({"fgi": {"score": 55, "zone": "Neutral"}}), 55.0)

    def test_returns_none_if_missing(self):
        self.assertIsNone(_get_fgi_score({"fgi": {}}))
        self.assertIsNone(_get_fgi_score({"fgi": {"score": None}}))

    def test_returns_none_if_invalid(self):
        self.assertIsNone(_get_fgi_score({"fgi": {"score": "invalid"}}))


# ── Signal counting ──────────────────────────────────────────────────────────

class TestOverheatSignals(unittest.TestCase):
    def test_no_signals(self):
        count = _count_overheat_signals(
            fgi=50, rsi=50, mfi=50, last_close=100,
            sma50=100, obv=None, obv_prev=None, upside_pct=20,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 0)

    def test_fgi_overheating(self):
        count = _count_overheat_signals(
            fgi=70, rsi=50, mfi=50, last_close=100,
            sma50=100, obv=None, obv_prev=None, upside_pct=20,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 1)

    def test_rsi_overheating(self):
        count = _count_overheat_signals(
            fgi=50, rsi=75, mfi=50, last_close=100,
            sma50=100, obv=None, obv_prev=None, upside_pct=20,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 1)

    def test_mfi_overheating(self):
        count = _count_overheat_signals(
            fgi=50, rsi=50, mfi=85, last_close=100,
            sma50=100, obv=None, obv_prev=None, upside_pct=20,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 1)

    def test_price_above_sma50(self):
        count = _count_overheat_signals(
            fgi=50, rsi=50, mfi=50, last_close=115,
            sma50=100, obv=None, obv_prev=None, upside_pct=20,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 1)

    def test_obv_divergence(self):
        count = _count_overheat_signals(
            fgi=50, rsi=50, mfi=50, last_close=115,
            sma50=100, obv=900000, obv_prev=1000000, upside_pct=20,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 2)  # price above SMA50 + OBV divergence

    def test_low_upside(self):
        count = _count_overheat_signals(
            fgi=50, rsi=50, mfi=50, last_close=100,
            sma50=100, obv=None, obv_prev=None, upside_pct=3,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 1)

    def test_multiple_signals(self):
        count = _count_overheat_signals(
            fgi=70, rsi=75, mfi=85, last_close=115,
            sma50=100, obv=None, obv_prev=None, upside_pct=3,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 5)

    def test_none_values_handled(self):
        count = _count_overheat_signals(
            fgi=None, rsi=None, mfi=None, last_close=None,
            sma50=None, obv=None, obv_prev=None, upside_pct=None,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 0)


class TestNegativeSignals(unittest.TestCase):
    def test_no_signals(self):
        count = _count_negative_signals(
            last_close=130, sma50=120, sma200=115,
            rsi=55, mfi=50, obv=1000000, obv_prev=1000000,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 0)

    def test_price_below_sma50(self):
        count = _count_negative_signals(
            last_close=110, sma50=120, sma200=100,
            rsi=55, mfi=50, obv=1000000, obv_prev=1000000,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 1)

    def test_price_below_sma200(self):
        count = _count_negative_signals(
            last_close=110, sma50=120, sma200=115,
            rsi=55, mfi=50, obv=1000000, obv_prev=1000000,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 2)

    def test_weak_rsi(self):
        count = _count_negative_signals(
            last_close=130, sma50=120, sma200=115,
            rsi=40, mfi=50, obv=1000000, obv_prev=1000000,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 1)

    def test_weak_mfi(self):
        count = _count_negative_signals(
            last_close=130, sma50=120, sma200=115,
            rsi=55, mfi=35, obv=1000000, obv_prev=1000000,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 1)

    def test_obv_declining(self):
        count = _count_negative_signals(
            last_close=130, sma50=120, sma200=115,
            rsi=55, mfi=50, obv=900000, obv_prev=1000000,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 1)

    def test_multiple_negative_signals(self):
        count = _count_negative_signals(
            last_close=105, sma50=120, sma200=115,
            rsi=35, mfi=30, obv=900000, obv_prev=1000000,
            signals=_RULES.get("signals", {}),
        )
        self.assertEqual(count, 5)


# ── Position evaluation ──────────────────────────────────────────────────────

class TestEvaluatePosition(unittest.TestCase):
    def test_nessuna_posizione(self):
        output = _base_output()
        pos = _position(quantity=0, unrealized_pnl_pct=0.0)
        result = evaluate_position("NVDA", pos, output, rules=_RULES)
        self.assertEqual(result.sell_signal, "NESSUNA POSIZIONE")
        self.assertEqual(result.confidence, "high")

    def test_mantieni_low_gain(self):
        output = _base_output()
        pos = _position(unrealized_pnl_pct=10.0)
        result = evaluate_position("NVDA", pos, output, rules=_RULES)
        self.assertEqual(result.sell_signal, "MANTIENI")
        self.assertEqual(result.confidence, "high")

    def test_tp1_base(self):
        output = _base_output()
        pos = _position(unrealized_pnl_pct=18.0)
        result = evaluate_position("NVDA", pos, output, rules=_RULES)
        self.assertEqual(result.sell_signal, "PRENDI PROFITTO PARZIALE")
        self.assertIn("18.0%", result.reasons[0])
        self.assertEqual(result.confidence, "medium")

    def test_tp2_rafforzato(self):
        output = _base_output()
        pos = _position(unrealized_pnl_pct=27.0)
        result = evaluate_position("NVDA", pos, output, rules=_RULES)
        self.assertEqual(result.sell_signal, "PRENDI PROFITTO PARZIALE")
        self.assertIn("27.0%", result.reasons[0])
        self.assertIn("Buy-the-Dip", result.reasons[1])

    def test_tp3_with_overheating(self):
        output = _base_output()
        output["fgi"]["score"] = 70
        output["indicators"]["tech"]["NVDA"]["rsi_14"] = 75
        output["indicators"]["tech"]["NVDA"]["mfi_14"] = 85
        pos = _position(unrealized_pnl_pct=35.0)
        result = evaluate_position("NVDA", pos, output, rules=_RULES)
        self.assertEqual(result.sell_signal, "RIDUCI ESPOSIZIONE")
        self.assertEqual(result.confidence, "high")
        self.assertIn("35.0%", result.reasons[0])
        # Should have overheating count in reasons
        self.assertTrue(any("surriscaldamento" in r.lower() for r in result.reasons))

    def test_tp3_without_overheating_not_triggered(self):
        output = _base_output()
        output["fgi"]["score"] = 30
        output["indicators"]["tech"]["NVDA"]["rsi_14"] = 40
        output["indicators"]["tech"]["NVDA"]["mfi_14"] = 30
        pos = _position(unrealized_pnl_pct=35.0)
        result = evaluate_position("NVDA", pos, output, rules=_RULES)
        # 35% > tp3 but only 1 overheat signal (upside_pct=20% < 10%)
        # Not enough (min=2)
        self.assertNotEqual(result.sell_signal, "RIDUCI ESPOSIZIONE")

    def test_attenzione_in_loss_with_negative_signals(self):
        output = _base_output()
        # Price below SMA50 and SMA200
        output["indicators"]["tech"]["NVDA"]["rsi_14"] = 40
        output["indicators"]["tech"]["NVDA"]["mfi_14"] = 35
        output["ohlcv"]["tech"]["NVDA"]["last_close"] = 105
        pos = _position(unrealized_pnl_pct=-5.0)
        result = evaluate_position("NVDA", pos, output, rules=_RULES)
        self.assertEqual(result.sell_signal, "ATTENZIONE")
        self.assertIn("5.0%", result.reasons[0])
        self.assertIn("perdita", result.reasons[0])

    def test_missing_data_does_not_crash(self):
        output = _base_output(indicators={}, ohlcv={}, valuation={})
        output["fgi"] = {}
        pos = _position(unrealized_pnl_pct=20.0)
        result = evaluate_position("NVDA", pos, output, rules=_RULES)
        # Should still produce a signal (TP1 even without indicators)
        self.assertEqual(result.sell_signal, "PRENDI PROFITTO PARZIALE")

    def test_empty_ticker_data(self):
        output = _base_output(indicators={}, ohlcv={}, valuation={})
        pos = _position(ticker="AAPL", unrealized_pnl_pct=20.0)
        result = evaluate_position("AAPL", pos, output, rules=_RULES)
        # No data found, but position has gain -> TP1
        self.assertEqual(result.sell_signal, "PRENDI PROFITTO PARZIALE")

    def test_negative_gain_at_tp1_threshold(self):
        """TP thresholds use >= so exactly at threshold should trigger."""
        output = _base_output()
        pos = _position(unrealized_pnl_pct=15.0)
        result = evaluate_position("NVDA", pos, output, rules=_RULES)
        self.assertEqual(result.sell_signal, "PRENDI PROFITTO PARZIALE")

    def test_below_tp1_is_mantieni(self):
        output = _base_output()
        pos = _position(unrealized_pnl_pct=14.9)
        result = evaluate_position("NVDA", pos, output, rules=_RULES)
        self.assertEqual(result.sell_signal, "MANTIENI")


# ── Evaluate all positions ───────────────────────────────────────────────────

class TestEvaluateAll(unittest.TestCase):
    def test_multiple_positions(self):
        output = _base_output()
        # Set up overheating for NVDA to trigger TP3
        output["fgi"]["score"] = 70
        output["indicators"]["tech"]["NVDA"]["rsi_14"] = 75
        output["indicators"]["tech"]["NVDA"]["mfi_14"] = 85
        positions = [
            _position(ticker="NVDA", unrealized_pnl_pct=35.0),
            _position(ticker="AAPL", quantity=50, avg_price=200.0, unrealized_pnl_pct=10.0),
        ]
        results = evaluate_all(positions, output, rules=_RULES)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].sell_signal, "RIDUCI ESPOSIZIONE")
        self.assertEqual(results[1].sell_signal, "MANTIENI")

    def test_empty_positions(self):
        output = _base_output()
        results = evaluate_all([], output, rules=_RULES)
        self.assertEqual(results, [])


# ── SellEvaluation dataclass ─────────────────────────────────────────────────

class TestSellEvaluation(unittest.TestCase):
    def test_defaults(self):
        ev = SellEvaluation(ticker="X", sell_signal="MANTIENI", confidence="high")
        self.assertEqual(ev.reasons, [])
        self.assertEqual(ev.suggested_action_note, "")

    def test_to_dict(self):
        ev = SellEvaluation(
            ticker="X",
            sell_signal="MANTIENI",
            confidence="high",
            reasons=["ok"],
            suggested_action_note="hold",
        )
        d = ev.__dict__
        self.assertEqual(d["ticker"], "X")
        self.assertEqual(d["sell_signal"], "MANTIENI")


if __name__ == "__main__":
    unittest.main()
