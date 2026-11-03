"""Unit tests for setup_type classification / buy_candidate / value_flag."""

from __future__ import annotations

import unittest

from setup_classifier import (
    BUY_CANDIDATE_SETUPS,
    DEFAULT_SETUP_THRESHOLDS,
    FGI_BUY_THRESHOLD,
    SETUP_CONTINUATION,
    SETUP_DEFENSIVE,
    SETUP_LABELS,
    SETUP_PULLBACK,
    SETUP_UNKNOWN,
    annotate_output,
    buy_candidate_reasons,
    compute_buy_candidate,
    compute_setup_type,
    compute_value_flag,
    is_defensive,
    load_setup_thresholds,
    ticker_is_fresh,
)


def _trend_entry(**overrides) -> dict:
    """Entry sopra entrambe le medie, drawdown contenuto (continuation)."""
    entry = {
        "last_close": 100.0,
        "sma_50": 95.0,
        "sma_200": 90.0,
        "rsi_14": 55.0,
        "mfi_14": 55.0,
        "drawdown_52w": -2.0,
        "status": "fresh",
    }
    entry.update(overrides)
    return entry


class TestComputeSetupType(unittest.TestCase):
    def test_trend_continuation(self):
        self.assertEqual(compute_setup_type(_trend_entry()), SETUP_CONTINUATION)

    def test_drawdown_exactly_at_threshold_is_continuation(self):
        # drawdown == -5 (soglia) → NON è più un rilevante rientro.
        entry = _trend_entry(drawdown_52w=DEFAULT_SETUP_THRESHOLDS["drawdown_pullback_pct"])
        self.assertEqual(compute_setup_type(entry), SETUP_CONTINUATION)

    def test_drawdown_just_below_threshold_is_pullback(self):
        entry = _trend_entry(drawdown_52w=-5.1)
        self.assertEqual(compute_setup_type(entry), SETUP_PULLBACK)

    def test_rsi_exactly_at_threshold_not_oversold(self):
        # RSI == 30 → non scarico: drawdown -2 → continuation.
        entry = _trend_entry(rsi_14=30.0)
        self.assertEqual(compute_setup_type(entry), SETUP_CONTINUATION)

    def test_rsi_just_below_threshold_is_pullback(self):
        entry = _trend_entry(rsi_14=29.9, drawdown_52w=-2.0)
        self.assertEqual(compute_setup_type(entry), SETUP_PULLBACK)

    def test_mfi_exactly_at_threshold_not_oversold(self):
        entry = _trend_entry(mfi_14=20.0)
        self.assertEqual(compute_setup_type(entry), SETUP_CONTINUATION)

    def test_mfi_just_below_threshold_is_pullback(self):
        entry = _trend_entry(mfi_14=19.9, drawdown_52w=-2.0)
        self.assertEqual(compute_setup_type(entry), SETUP_PULLBACK)

    def test_below_sma50_is_unknown(self):
        entry = _trend_entry(last_close=94.0)  # < sma_50 95.0
        self.assertEqual(compute_setup_type(entry), SETUP_UNKNOWN)

    def test_below_sma200_is_unknown(self):
        entry = _trend_entry(last_close=89.0)  # < sma_200 90.0
        self.assertEqual(compute_setup_type(entry), SETUP_UNKNOWN)

    def test_price_equal_to_smas_is_in_trend(self):
        entry = _trend_entry(last_close=95.0, sma_50=95.0, sma_200=90.0)
        self.assertEqual(compute_setup_type(entry), SETUP_CONTINUATION)

    def test_missing_sma_is_unknown(self):
        entry = _trend_entry()
        del entry["sma_200"]
        self.assertEqual(compute_setup_type(entry), SETUP_UNKNOWN)

    def test_missing_price_is_unknown(self):
        entry = _trend_entry()
        del entry["last_close"]
        self.assertEqual(compute_setup_type(entry), SETUP_UNKNOWN)

    def test_missing_drawdown_without_oversold_is_unknown(self):
        entry = _trend_entry()
        del entry["drawdown_52w"]
        self.assertEqual(compute_setup_type(entry), SETUP_UNKNOWN)

    def test_missing_drawdown_with_oversold_is_pullback(self):
        entry = _trend_entry(rsi_14=25.0)
        del entry["drawdown_52w"]
        self.assertEqual(compute_setup_type(entry), SETUP_PULLBACK)

    def test_empty_entry_is_unknown(self):
        self.assertEqual(compute_setup_type({}), SETUP_UNKNOWN)

    def test_defensive_marker_wins_even_above_medians(self):
        entry = _trend_entry()
        self.assertEqual(
            compute_setup_type(entry, defensive=True), SETUP_DEFENSIVE
        )

    def test_defensive_marker_wins_with_missing_data(self):
        self.assertEqual(compute_setup_type({}, defensive=True), SETUP_DEFENSIVE)

    def test_valuation_never_participates(self):
        # upside_pct forte non cambia la classificazione (display-only).
        without = compute_setup_type(_trend_entry())
        with_upside = compute_setup_type(_trend_entry(upside_pct=99.0))
        self.assertEqual(without, with_upside)

    def test_custom_thresholds_override_defaults(self):
        th = {"drawdown_pullback_pct": -10}
        # -7 > -10 → continuation con soglia custom, pullback con default.
        entry = _trend_entry(drawdown_52w=-7.0)
        self.assertEqual(compute_setup_type(entry, th), SETUP_CONTINUATION)
        self.assertEqual(compute_setup_type(entry), SETUP_PULLBACK)

    def test_setup_labels_cover_all_values(self):
        for setup in (SETUP_PULLBACK, SETUP_CONTINUATION, SETUP_DEFENSIVE, SETUP_UNKNOWN):
            self.assertIn(setup, SETUP_LABELS)


class TestBuyCandidate(unittest.TestCase):
    def _open_gate(self, score=20.0, fresh=True, setup=SETUP_CONTINUATION, ticker_fresh=True):
        return compute_buy_candidate(
            setup, fgi_score=score, fgi_fresh=fresh, ticker_fresh=ticker_fresh
        )

    def test_open_gate_with_idoneous_setup_is_candidate(self):
        self.assertTrue(self._open_gate())

    def test_gate_boundary_25_is_open(self):
        self.assertTrue(self._open_gate(score=FGI_BUY_THRESHOLD))

    def test_gate_closed_above_25(self):
        # 25 < FGI ≤ 40 → watchlist, > 40 → nessun BUY: mai candidato.
        self.assertFalse(self._open_gate(score=26.0))
        self.assertFalse(self._open_gate(score=41.0))

    def test_unknown_setup_never_candidate_even_open_gate(self):
        self.assertFalse(self._open_gate(setup=SETUP_UNKNOWN))

    def test_defensive_setup_never_candidate(self):
        self.assertFalse(self._open_gate(setup=SETUP_DEFENSIVE))

    def test_stale_ticker_is_not_candidate(self):
        self.assertFalse(self._open_gate(ticker_fresh=False))

    def test_stale_fgi_is_not_candidate(self):
        self.assertFalse(self._open_gate(fresh=False))

    def test_missing_fgi_is_not_candidate(self):
        self.assertFalse(
            compute_buy_candidate(
                SETUP_CONTINUATION, fgi_score=None, fgi_fresh=True,
                ticker_fresh=True,
            )
        )

    def test_pullback_also_eligible(self):
        self.assertTrue(self._open_gate(setup=SETUP_PULLBACK))

    def test_buy_candidate_set_matches_spec(self):
        self.assertEqual(
            BUY_CANDIDATE_SETUPS, frozenset({SETUP_PULLBACK, SETUP_CONTINUATION})
        )

    def test_value_flag_does_not_alter_buy_candidate(self):
        # value_flag è display-only: stesso risultato con upside qualsiasi.
        base = dict(fgi_score=20.0, fgi_fresh=True, ticker_fresh=True)
        for upside in (12.0, 0.0, -8.0, None):
            entry = _trend_entry() if upside is None else _trend_entry(upside_pct=upside)
            setup = compute_setup_type(entry)
            self.assertTrue(compute_buy_candidate(setup, **base))

    def test_reasons_mention_gate_setup_and_freshness(self):
        reasons = buy_candidate_reasons(
            SETUP_CONTINUATION, fgi_score=20.0, fgi_fresh=True, ticker_fresh=True
        )
        joined = " ".join(reasons)
        self.assertIn("idoneo", joined)
        self.assertIn("gate FGI aperto", joined)
        self.assertIn("freschi", joined)

    def test_reasons_fail_closed_wording(self):
        reasons = buy_candidate_reasons(
            SETUP_UNKNOWN, fgi_score=None, fgi_fresh=False, ticker_fresh=False
        )
        joined = " ".join(reasons)
        self.assertIn("non idoneo", joined)
        self.assertIn("fail-closed", joined)
        self.assertIn("stale", joined)


class TestValueFlag(unittest.TestCase):
    def test_positive_upside(self):
        self.assertEqual(compute_value_flag({"upside_pct": 5.2}), "upside > 0")

    def test_zero_upside(self):
        self.assertEqual(compute_value_flag({"upside_pct": 0}), "upside ≤ 0")

    def test_negative_upside(self):
        self.assertEqual(compute_value_flag({"upside_pct": -3.0}), "upside ≤ 0")

    def test_missing_upside(self):
        self.assertEqual(compute_value_flag({}), "n/d")


class TestLoadSetupThresholds(unittest.TestCase):
    def test_defaults_when_config_missing(self):
        th = load_setup_thresholds(None)
        self.assertEqual(th["drawdown_pullback_pct"], -5)
        self.assertEqual(th["rsi_oversold"], 30)
        self.assertEqual(th["mfi_oversold"], 20)
        self.assertEqual(th["defensive_symbols"], [])

    def test_config_overrides_defaults(self):
        config = {"strategy": {"setup_type": {
            "drawdown_pullback_pct": -10,
            "mfi_oversold": 25,
            "defensive_symbols": ["NEE", "arcc"],
        }}}
        th = load_setup_thresholds(config)
        self.assertEqual(th["drawdown_pullback_pct"], -10)
        self.assertEqual(th["mfi_oversold"], 25)
        self.assertEqual(th["rsi_oversold"], 30)  # non toccato → default
        self.assertEqual(th["defensive_symbols"], ["NEE", "arcc"])

    def test_invalid_values_fall_back_to_defaults(self):
        config = {"strategy": {"setup_type": {
            "drawdown_pullback_pct": "low",
            "rsi_oversold": True,  # bool espressamente scartato
            "defensive_symbols": "NEE",  # non una lista
        }}}
        th = load_setup_thresholds(config)
        self.assertEqual(th["drawdown_pullback_pct"], -5)
        self.assertEqual(th["rsi_oversold"], 30)
        self.assertEqual(th["defensive_symbols"], [])


class TestIsDefensive(unittest.TestCase):
    def test_case_insensitive_match(self):
        th = {"defensive_symbols": ["NEE", "ARCC"]}
        self.assertTrue(is_defensive("nee", th))
        self.assertTrue(is_defensive("ARCC", th))
        self.assertFalse(is_defensive("NVDA", th))

    def test_empty_thresholds(self):
        self.assertFalse(is_defensive("NEE", None))


class TestAnnotateOutput(unittest.TestCase):
    def _output(self, **fgi):
        fgi_default = {"score": 20.0, "status": "fresh"}
        fgi_default.update(fgi)
        return {
            "fgi": fgi_default,
            "indicators": {"utilities": {"NEE": {
                "rsi_14": 55.0, "mfi_14": 55.0, "last_close": 100.0,
                "sma_50": 95.0, "sma_200": 90.0, "drawdown_52w": -2.0,
                "status": "fresh",
            }}},
            "ohlcv": {"utilities": {"NEE": {"last_close": 100.0, "status": "fresh"}}},
            "valuation": {"utilities": {"NEE": {"upside_pct": 12.0}}},
        }

    def test_writes_three_fields_into_indicators_entry(self):
        output = annotate_output(self._output(), {"strategy": {"setup_type": {
            "defensive_symbols": [],
        }}})
        entry = output["indicators"]["utilities"]["NEE"]
        self.assertEqual(entry["setup_type"], SETUP_CONTINUATION)
        self.assertIs(entry["buy_candidate"], True)
        self.assertEqual(entry["value_flag"], "upside > 0")

    def test_defensive_symbol_from_config(self):
        output = annotate_output(self._output(), {"strategy": {"setup_type": {
            "defensive_symbols": ["NEE"],
        }}})
        entry = output["indicators"]["utilities"]["NEE"]
        self.assertEqual(entry["setup_type"], SETUP_DEFENSIVE)
        self.assertIs(entry["buy_candidate"], False)

    def test_stale_fgi_blocks_buy_candidate(self):
        output = annotate_output(self._output(status="stale"))
        entry = output["indicators"]["utilities"]["NEE"]
        self.assertIs(entry["buy_candidate"], False)

    def test_annotates_ohlcv_only_ticker(self):
        output = {
            "fgi": {"score": 20.0, "status": "fresh"},
            "ohlcv": {"tech": {"XYZ": {"last_close": 50.0, "status": "fresh"}}},
        }
        annotate_output(output, None)
        entry = output["ohlcv"]["tech"]["XYZ"]
        self.assertEqual(entry["setup_type"], SETUP_UNKNOWN)  # mancano medie
        self.assertIs(entry["buy_candidate"], False)
        self.assertEqual(entry["value_flag"], "n/d")

    def test_value_flag_from_valuation_section(self):
        output = self._output()
        output["valuation"]["utilities"]["NEE"]["upside_pct"] = -4.0
        annotate_output(output, None)
        self.assertEqual(
            output["indicators"]["utilities"]["NEE"]["value_flag"], "upside ≤ 0"
        )


class TestFreshness(unittest.TestCase):
    def test_fresh(self):
        self.assertTrue(ticker_is_fresh({"status": "fresh"}))

    def test_stale_and_missing(self):
        self.assertFalse(ticker_is_fresh({"status": "stale"}))
        self.assertFalse(ticker_is_fresh({}))
        self.assertFalse(ticker_is_fresh(None))


if __name__ == "__main__":
    unittest.main()
