"""Unit tests for the static HTML report generator (pure functions)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from report_html import (
    _age_attrs,
    build_page,
    buy_the_dip_gate,
    compute_signal,
    final_action,
    fmt,
    format_iso_dt,
    market_regime,
    render,
    render_indicator_matrix,
    render_legend,
    render_market_cards,
    render_stale_summary,
    render_ticker_table,
    semaphore_class,
    technical_signal,
)


def _sample_data() -> dict:
    return {
        "generated_at": "2026-08-12T14:30:07+00:00",
        "fgi": {"score": 62.65, "zone": "greed", "fetched_at": "2026-08-12T14:29:42+00:00",
                "frequency": "daily", "stale_after_hours": 24, "status": "fresh"},
        "aaii": {"bullish": 37.0, "bearish": 38.0, "neutral": 25.0,
                 "fetched_at": "2026-08-12T14:29:43+00:00",
                 "frequency": "weekly", "stale_after_hours": 168, "status": "fresh",
                 "next_expected": "2026-08-13"},
        "vix": {"vix_close": 15.28, "fetched_at": "2026-08-12T14:29:44+00:00",
                "frequency": "daily", "stale_after_hours": 24, "status": "fresh"},
        "pcr": {"equity_pcr": 0.63, "total_pcr": 0.81, "index_pcr": 0.90,
                "trade_date": "2026-08-11", "fetched_at": "2026-08-12T00:00:00+00:00",
                "frequency": "daily", "stale_after_hours": 24, "status": "fresh"},
        "ohlcv": {
            "semiconductors": {
                "AMAT": {"symbol": "AMAT", "name": "Applied Materials",
                         "last_close": 548.87, "last_date": "2026-08-12",
                         "fetched_at": "2026-08-12T14:30:06+00:00",
                         "frequency": "daily", "stale_after_hours": 24, "status": "fresh"}
            }
        },
        "indicators": {
            "semiconductors": {
                "AMAT": {"rsi_14": 52.08, "obv": 356286653.0, "mfi_14": 34.97,
                         "sma_50": 557.88, "sma_200": 385.3, "drawdown_52w": -24.08,
                         "symbol": "AMAT", "name": "Applied Materials",
                         "fetched_at": "2026-08-12T14:30:06+00:00",
                         "frequency": "daily", "stale_after_hours": 24, "status": "fresh"}
            }
        },
        "stale_summary": {"total_sources": 5, "fresh": 5, "stale": 0,
                          "stale_details": [], "signal_reliability": "high"},
        "strategy_indicators": {
            "fgi": {"name": "Fear & Greed Index", "strategy_ref": "F1 (Regola 0)",
                    "implementation_status": "implemented", "coverage": True,
                    "availability": True, "usable_in_strategy_score": True,
                    "semantic_coherent": True, "source": "scraped",
                    "primary_source": "CNN API", "notes": ""},
            "nyse_nh_nl": {"name": "NYSE New Highs/New Lows", "strategy_ref": "F3/#12",
                           "implementation_status": "implemented", "coverage": True,
                           "availability": True, "usable_in_strategy_score": True,
                           "semantic_coherent": True, "source": "scraped",
                           "primary_source": "Barchart", "notes": ""},
        },
    }


class TestSemaphoreClass(unittest.TestCase):
    def test_rsi_overbought(self):
        self.assertEqual(semaphore_class(75.0, "rsi"), "overbought")

    def test_rsi_oversold(self):
        self.assertEqual(semaphore_class(25.0, "rsi"), "oversold")

    def test_rsi_neutral(self):
        self.assertEqual(semaphore_class(50.0, "rsi"), "neutral")

    def test_mfi_overbought(self):
        self.assertEqual(semaphore_class(85.0, "mfi"), "overbought")

    def test_drawdown_critical(self):
        self.assertEqual(semaphore_class(-20.0, "drawdown"), "critical")

    def test_drawdown_warning(self):
        self.assertEqual(semaphore_class(-10.0, "drawdown"), "warning")

    def test_drawdown_ok(self):
        self.assertEqual(semaphore_class(-2.0, "drawdown"), "ok")

    def test_none_is_neutral(self):
        self.assertEqual(semaphore_class(None, "rsi"), "neutral")


class TestFormat(unittest.TestCase):
    def test_format_iso_dt(self):
        self.assertEqual(format_iso_dt("2026-08-12T14:30:07+00:00"), "12 ago 2026, 14:30")

    def test_fmt_number(self):
        self.assertEqual(fmt(548.87), "548.87")

    def test_fmt_none(self):
        self.assertEqual(fmt(None), "—")


class TestComputeSignal(unittest.TestCase):
    def test_buy_on_oversold_convergence(self):
        entry = {
            "last_close": 100.0,
            "rsi_14": 25.0,    # oversold → +1
            "mfi_14": 15.0,    # oversold → +1
            "sma_50": 90.0,    # price sopra → +1
            "sma_200": 80.0,   # price sopra → +1
            "drawdown_52w": -2.0,  # ok → +1
        }
        # FGI 20 (paura sufficiente) → il buy tecnico resta valido
        self.assertEqual(compute_signal(entry, fgi_score=20), "buy")

    def test_watchlist_on_deep_weakness(self):
        entry = {
            "last_close": 100.0,
            "rsi_14": 75.0,    # overbought → -1
            "mfi_14": 85.0,    # overbought → -1
            "sma_50": 110.0,   # price sotto → -1
            "sma_200": 120.0,  # price sotto → -1
            "drawdown_52w": -20.0,  # critical → -1
        }
        # La debolezza profonda è il profilo buy-the-dip → WATCHLIST, MAI sell
        self.assertEqual(compute_signal(entry), "watchlist")

    def test_hold_on_mixed_signals(self):
        entry = {
            "last_close": 100.0,
            "rsi_14": 50.0,    # neutro → 0
            "mfi_14": 50.0,    # neutro → 0
            "sma_50": 110.0,   # price sotto → -1
            "sma_200": 80.0,   # price sopra → +1
            "drawdown_52w": -8.0,  # warning → 0
        }
        self.assertEqual(compute_signal(entry), "hold")

    def test_missing_indicators_do_not_crash(self):
        entry = {"last_close": 100.0}
        self.assertEqual(compute_signal(entry), "hold")

    def test_signal_badge_in_table(self):
        data = _sample_data()
        entries = data["indicators"]["semiconductors"]
        with_weak = dict(entries["AMAT"], rsi_14=80.0, mfi_14=90.0,
                         sma_50=600.0, sma_200=600.0, drawdown_52w=-30.0)
        html = render_ticker_table("semiconductors", {"AMAT": with_weak})
        self.assertIn('class="signal watchlist"', html)
        self.assertIn("OSSERVA", html)

    def test_market_regime_classification(self):
        self.assertEqual(market_regime(70.0), "greed")
        self.assertEqual(market_regime(60.0), "greed")
        # Confine strategia F1: Neutral 45-55, Greed 56-74 → 55 è neutral
        self.assertEqual(market_regime(55.0), "neutral")
        self.assertEqual(market_regime(50.0), "neutral")
        self.assertEqual(market_regime(44.0), "fear")
        self.assertEqual(market_regime(30.0), "fear")
        self.assertEqual(market_regime(None), "neutral")

    def test_gate_blocks_buy_in_greed(self):
        entry = {
            "last_close": 100.0,
            "rsi_14": 25.0,
            "mfi_14": 15.0,
            "sma_50": 90.0,
            "sma_200": 80.0,
            "drawdown_52w": -2.0,
        }
        # Senza gate → buy; con regime greed → bloccato a hold
        self.assertEqual(compute_signal(entry, "neutral", fgi_score=20), "buy")
        self.assertEqual(compute_signal(entry, "greed", fgi_score=60), "hold")

    def test_watchlist_survives_in_fear(self):
        entry = {
            "last_close": 100.0,
            "rsi_14": 75.0,
            "mfi_14": 85.0,
            "sma_50": 110.0,
            "sma_200": 120.0,
            "drawdown_52w": -20.0,
        }
        # In fear la debolezza resta watchlist (sconti più reali), mai sell
        self.assertEqual(compute_signal(entry, "neutral"), "watchlist")
        self.assertEqual(compute_signal(entry, "fear"), "watchlist")

    def test_gate_allows_aligned_signals(self):
        entry_buy = {
            "last_close": 100.0,
            "rsi_14": 25.0,
            "mfi_14": 15.0,
            "sma_50": 90.0,
            "sma_200": 80.0,
            "drawdown_52w": -2.0,
        }
        entry_weak = {
            "last_close": 100.0,
            "rsi_14": 75.0,
            "mfi_14": 85.0,
            "sma_50": 110.0,
            "sma_200": 120.0,
            "drawdown_52w": -20.0,
        }
        # fear favorisce buy; la debolezza resta watchlist in ogni regime
        self.assertEqual(compute_signal(entry_buy, "fear", fgi_score=20), "buy")
        self.assertEqual(compute_signal(entry_weak, "greed", fgi_score=60), "watchlist")

    def _buy_entry(self) -> dict:
        return {
            "last_close": 100.0,
            "rsi_14": 25.0,
            "mfi_14": 15.0,
            "sma_50": 90.0,
            "sma_200": 80.0,
            "drawdown_52w": -2.0,
        }

    def test_fgi_gate_none_blocks_buy(self):
        # FGI mancante/stale → fail-closed: nessun BUY
        self.assertEqual(compute_signal(self._buy_entry(), fgi_score=None), "hold")

    def test_fgi_gate_53_57_blocks_buy(self):
        # FGI 53.57 (neutral) → BUY tecnico diventa ATTENDI
        self.assertEqual(compute_signal(self._buy_entry(), fgi_score=53.57), "hold")

    def test_fgi_gate_41_blocks_buy(self):
        # FGI 41 (> 40) → BUY tecnico diventa ATTENDI
        self.assertEqual(compute_signal(self._buy_entry(), fgi_score=41), "hold")

    def test_fgi_gate_40_is_watchlist(self):
        # FGI 40 (25 < FGI <= 40) → BUY tecnico diventa WATCHLIST
        self.assertEqual(compute_signal(self._buy_entry(), fgi_score=40), "watchlist")

    def test_fgi_gate_30_is_watchlist(self):
        # FGI 30 (25 < FGI <= 40) → BUY tecnico diventa WATCHLIST
        self.assertEqual(compute_signal(self._buy_entry(), fgi_score=30), "watchlist")

    def test_fgi_gate_25_allows_buy(self):
        # FGI 25 (<= 25) → BUY tecnico resta BUY
        self.assertEqual(compute_signal(self._buy_entry(), fgi_score=25), "buy")

    def test_fgi_gate_20_allows_buy(self):
        # FGI 20 (<= 25) → BUY tecnico resta BUY
        self.assertEqual(compute_signal(self._buy_entry(), fgi_score=20), "buy")

    def test_fgi_gate_never_upgrades_non_buy(self):
        # Segnali non-buy non devono MAI diventare buy, qualunque sia il FGI
        weak = {
            "last_close": 100.0,
            "rsi_14": 75.0,
            "mfi_14": 85.0,
            "sma_50": 110.0,
            "sma_200": 120.0,
            "drawdown_52w": -20.0,
        }
        mixed = {
            "last_close": 100.0,
            "rsi_14": 50.0,
            "mfi_14": 50.0,
            "sma_50": 110.0,
            "sma_200": 80.0,
            "drawdown_52w": -8.0,
        }
        for fgi in (None, 10, 20, 25, 30, 40, 41, 53.57, 70):
            self.assertEqual(compute_signal(weak, fgi_score=fgi), "watchlist")
            self.assertEqual(compute_signal(mixed, fgi_score=fgi), "hold")

    def test_table_fgi_53_57_renders_no_compra(self):
        # Con FGI 53.57 nessun ticker tecnicamente buy deve renderizzare
        # VALUTA INGRESSO (nessun segnale di ingresso)
        data = _sample_data()
        data["fgi"]["score"] = 53.57
        data["fgi"]["status"] = "fresh"
        entries = data["indicators"]["semiconductors"]
        strong = dict(entries["AMAT"], rsi_14=25.0, mfi_14=15.0,
                      last_close=560.0, sma_50=500.0, sma_200=400.0,
                      drawdown_52w=-1.0)
        html = render_ticker_table("semiconductors", {"AMAT": strong},
                                   regime="neutral", fgi_score=53.57)
        self.assertIn("ATTENDI", html)
        self.assertNotIn("VALUTA INGRESSO", html)

    def test_compute_signal_delegates_to_pipeline(self):
        # Compatibilità: compute_signal == technical_signal + gate + final_action
        entry = self._buy_entry()
        for fgi in (None, 53.57, 30, 25, 20):
            gate = buy_the_dip_gate(fgi)
            expected = final_action(technical_signal(entry), gate)
            self.assertEqual(compute_signal(entry, fgi_score=fgi), expected)

    def test_scorer_accepts_proxy_accepted_parameter(self):
        # Guardia proxy (audit 2026-08-14): il parametro esiste e non cambia il
        # segnale — il motore consuma solo indicatori implemented per-ticker.
        entry = {
            "last_close": 100.0,
            "rsi_14": 25.0,
            "mfi_14": 15.0,
            "sma_50": 90.0,
            "sma_200": 80.0,
            "drawdown_52w": -2.0,
        }
        self.assertEqual(
            compute_signal(entry, "neutral", proxy_accepted={"vix_spot"}, fgi_score=20),
            compute_signal(entry, "neutral", fgi_score=20),
        )

    def test_table_uses_market_regime(self):
        data = _sample_data()
        data["fgi"]["score"] = 70.0  # greed
        entries = data["indicators"]["semiconductors"]
        # Titolo tecnicamente forte → in greed NON deve comparire VALUTA INGRESSO
        strong = dict(entries["AMAT"], rsi_14=50.0, mfi_14=50.0,
                      last_close=560.0, sma_50=500.0, sma_200=400.0,
                      drawdown_52w=-1.0)
        html = render_ticker_table("semiconductors", {"AMAT": strong}, regime="greed")
        self.assertIn("ATTENDI", html)
        self.assertNotIn("VALUTA INGRESSO", html)

    def test_qcom_case_is_watchlist_not_sell(self):
        # Regressione: il caso QCOM (deep weakness + greed) NON deve essere sell
        qcom = {
            "last_close": 163.52,
            "rsi_14": 45.15,
            "mfi_14": 28.65,
            "obv": 246045318,
            "sma_50": 187.05,
            "sma_200": 167.77,
            "drawdown_52w": -34.62,
        }
        # FGI 62.66 → greed
        self.assertEqual(market_regime(62.66), "greed")
        self.assertEqual(compute_signal(qcom, "greed"), "watchlist")
        self.assertNotEqual(compute_signal(qcom, "greed"), "sell")


class TestTechnicalSignal(unittest.TestCase):
    def _bullish_entry(self) -> dict:
        return {
            "last_close": 100.0,
            "rsi_14": 25.0,    # oversold → +1
            "mfi_14": 15.0,    # oversold → +1
            "sma_50": 90.0,    # price sopra → +1
            "sma_200": 80.0,   # price sopra → +1
            "drawdown_52w": -2.0,  # ok → +1
        }

    def _weak_entry(self) -> dict:
        return {
            "last_close": 100.0,
            "rsi_14": 75.0,    # overbought → -1
            "mfi_14": 85.0,    # overbought → -1
            "sma_50": 110.0,   # price sotto → -1
            "sma_200": 120.0,  # price sotto → -1
            "drawdown_52w": -20.0,  # critical → -1
        }

    def _neutral_entry(self) -> dict:
        return {
            "last_close": 100.0,
            "rsi_14": 50.0,    # neutro → 0
            "mfi_14": 50.0,    # neutro → 0
            "sma_50": 110.0,   # price sotto → -1
            "sma_200": 80.0,   # price sopra → +1
            "drawdown_52w": -8.0,  # warning → 0
        }

    def test_bullish_on_oversold_convergence(self):
        self.assertEqual(technical_signal(self._bullish_entry()), "bullish")

    def test_weak_on_deep_weakness(self):
        self.assertEqual(technical_signal(self._weak_entry()), "weak")

    def test_neutral_on_mixed_signals(self):
        self.assertEqual(technical_signal(self._neutral_entry()), "neutral")

    def test_missing_indicators_are_neutral(self):
        self.assertEqual(technical_signal({"last_close": 100.0}), "neutral")

    def test_technical_signal_ignores_market_gate(self):
        # La valutazione tecnica NON dipende dal FGI/regime
        self.assertEqual(technical_signal(self._bullish_entry()), "bullish")


class TestFinalAction(unittest.TestCase):
    def test_bullish_closed_is_hold(self):
        self.assertEqual(final_action("bullish", "closed"), "hold")

    def test_bullish_missing_or_stale_is_hold(self):
        self.assertEqual(final_action("bullish", "missing_or_stale"), "hold")

    def test_bullish_watch_only_is_watchlist(self):
        self.assertEqual(final_action("bullish", "watch_only"), "watchlist")

    def test_bullish_open_is_buy(self):
        self.assertEqual(final_action("bullish", "open"), "buy")

    def test_bullish_strong_open_is_buy(self):
        self.assertEqual(final_action("bullish", "strong_open"), "buy")

    def test_neutral_is_hold_regardless_of_gate(self):
        for gate in ("closed", "missing_or_stale", "watch_only", "open", "strong_open"):
            self.assertEqual(final_action("neutral", gate), "hold")

    def test_weak_is_watchlist_never_buy(self):
        for gate in ("closed", "missing_or_stale", "watch_only", "open", "strong_open"):
            self.assertEqual(final_action("weak", gate), "watchlist")


class TestBuyTheDipGate(unittest.TestCase):
    def test_none_is_missing_or_stale(self):
        self.assertEqual(buy_the_dip_gate(None), "missing_or_stale")

    def test_53_57_is_closed(self):
        self.assertEqual(buy_the_dip_gate(53.57), "closed")

    def test_41_is_closed(self):
        self.assertEqual(buy_the_dip_gate(41), "closed")

    def test_40_is_watch_only(self):
        self.assertEqual(buy_the_dip_gate(40), "watch_only")

    def test_30_is_watch_only(self):
        self.assertEqual(buy_the_dip_gate(30), "watch_only")

    def test_25_is_open(self):
        self.assertEqual(buy_the_dip_gate(25), "open")

    def test_20_is_strong_open(self):
        self.assertEqual(buy_the_dip_gate(20), "strong_open")

    def test_below_20_is_strong_open(self):
        self.assertEqual(buy_the_dip_gate(15), "strong_open")

    def test_stale_flag_forces_missing_or_stale(self):
        # stale=True vince sul punteggio (fail-closed)
        self.assertEqual(buy_the_dip_gate(20, stale=True), "missing_or_stale")
        self.assertEqual(buy_the_dip_gate(None, stale=True), "missing_or_stale")

    def test_non_numeric_is_missing_or_stale(self):
        self.assertEqual(buy_the_dip_gate("abc"), "missing_or_stale")
        self.assertEqual(buy_the_dip_gate("53.57"), "missing_or_stale")


class TestRenderSections(unittest.TestCase):
    def test_market_cards_contains_values(self):
        html = render_market_cards(_sample_data())
        self.assertIn("Fear &amp; Greed", html)
        self.assertIn("62.65", html)
        self.assertIn("15.28", html)
        self.assertIn("37", html)

    def test_market_cards_vix_term_structure_is_primary_when_available(self):
        # F3/#10: il term structure (M1/M2) è l'indicatore strategico → deve
        # essere il valore principale della card, con VIX spot come nota.
        data = _sample_data()
        data["vix_term_structure"] = {
            "m1": 18.2, "m2": 19.7, "structure": "contango",
            "contango_pct_1_2": 8.24, "fetched_at": "2026-08-12T14:29:45+00:00",
            "stale_after_hours": 24, "status": "fresh", "origin": "manual",
        }
        html = render_market_cards(data)
        self.assertIn("VIX Term Structure", html)
        self.assertIn("contango", html)
        self.assertIn("M1 18.20", html)
        self.assertIn("M2 19.70", html)
        # VIX spot resta come nota informativa, non come valore principale.
        self.assertIn("VIX spot", html)
        self.assertIn("15.28", html)

    def test_market_cards_vix_spot_fallback_when_no_term_structure(self):
        # Senza term structure la card mostra VIX spot (proxy) come fallback.
        html = render_market_cards(_sample_data())
        self.assertIn("VIX Spot", html)
        self.assertIn("proxy", html)
        self.assertIn("15.28", html)

    def test_market_cards_vix_error_when_both_missing(self):
        data = _sample_data()
        data["vix"] = {"status": "error", "error": "CBOE unreachable"}
        data["vix_term_structure"] = {"status": "error", "error": "no manual"}
        html = render_market_cards(data)
        self.assertIn("errore", html)

    def test_market_cards_shows_fgi_source(self):
        data = _sample_data()
        data["fgi"]["source"] = "feargreedmeter"
        html = render_market_cards(data)
        self.assertIn("Fonte: feargreedmeter", html)

    def test_market_cards_shows_aaii_source(self):
        data = _sample_data()
        data["aaii"]["source"] = "html_bars"
        html = render_market_cards(data)
        self.assertIn("Fonte: html_bars", html)

    def test_market_cards_escapes_source(self):
        # La fonte è testo libero dal modulo → va escapata nell'HTML
        data = _sample_data()
        data["fgi"]["source"] = "<b>x</b>"
        html = render_market_cards(data)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)
        self.assertNotIn("<b>x</b>", html)

    def test_market_cards_shows_error_badge_for_failed_source(self):
        data = _sample_data()
        data["fgi"] = {"status": "error", "error": "All sources failed"}
        html = render_market_cards(data)
        self.assertIn("errore", html)
        self.assertIn("All sources failed", html)

    def test_market_cards_include_age_attrs(self):
        html = render_market_cards(_sample_data())
        self.assertIn('data-fetched-at="2026-08-12T14:29:42+00:00"', html)  # fgi
        self.assertIn('data-stale-hours="24"', html)  # fgi
        self.assertIn('data-fetched-at="2026-08-12T14:29:43+00:00"', html)  # aaii
        self.assertIn('data-stale-hours="168"', html)  # aaii

    def test_error_card_has_no_age_attrs(self):
        data = _sample_data()
        data["fgi"] = {"status": "error", "error": "All sources failed"}
        html = render_market_cards(data)
        # La card di errore non ha timestamp → nessun data-fetched-at per fgi
        self.assertNotIn('data-fetched-at="2026-08-12T14:29:42+00:00"', html)

    def test_fgi_card_shows_components_grid(self):
        data = _sample_data()
        data["fgi"]["fgi_components"] = {
            "market_momentum": {"score": 74.6, "rating": "greed"},
            "stock_price_strength": {"score": 28.6, "rating": "fear"},
        }
        html = render_market_cards(data)
        self.assertIn("fgi-components", html)
        self.assertIn("Market Momentum", html)
        self.assertIn("74.6", html)
        self.assertIn("Stock Price Strength", html)
        self.assertIn("28.6", html)

    def test_fgi_card_without_components_no_grid(self):
        html = render_market_cards(_sample_data())
        self.assertNotIn("fgi-components", html)

    def test_fgi_rating_badge_escapes_class(self):
        from report_html import _fgi_rating_badge
        badge = _fgi_rating_badge('greed" onmouseover="alert(1)')
        # La classe non deve contenere un attributo iniettabile: html.escape
        # converte le virgolette in &quot;, quindi la sequenza esatta
        # `class="sema greed" onmouseover` non deve comparire.
        self.assertNotIn('class="sema greed" onmouseover', badge)
        self.assertIn('&quot;_onmouseover=&quot;', badge)

    def test_stale_summary_shows_error_count(self):
        summary = {
            "total_sources": 2,
            "fresh": 1,
            "stale": 1,
            "errors": 1,
            "stale_details": ["aaii: error (AAII fetch failed)"],
            "signal_reliability": "low",
        }
        html = render_stale_summary(summary)
        self.assertIn("1 errore", html)
        self.assertIn("low", html)
        self.assertIn("AAII fetch failed", html)

    def test_indicator_matrix_renders_status_badges(self):
        matrix = {
            "_meta": {"proxy_accepted": []},
            "summary": {"implemented": ["fgi"], "proxy": ["vix_spot"], "missing": ["nyse_nh_nl"]},
            "fgi": {"name": "Fear & Greed Index", "strategy_ref": "F1", "implementation_status": "implemented",
                    "semantic_coherent": True, "coverage": True, "availability": True,
                    "usable_in_strategy_score": True, "source": "scraped",
                    "primary_source": "CNN API", "notes": ""},
            "vix_spot": {"name": "VIX spot", "strategy_ref": "artefatto informativo", "implementation_status": "proxy",
                         "semantic_coherent": False, "coverage": False, "availability": True,
                         "usable_in_strategy_score": False, "source": "scraped",
                         "primary_source": "CBOE", "notes": "proxy"},
            "nyse_nh_nl": {"name": "NYSE NH-NL", "strategy_ref": "F3/#12", "implementation_status": "missing",
                           "semantic_coherent": False, "coverage": True, "availability": False,
                           "usable_in_strategy_score": False, "source": "missing",
                           "primary_source": None, "notes": "gap"},
        }
        html = render_indicator_matrix(matrix)
        self.assertIn("implemented", html)
        self.assertIn("proxy", html)
        self.assertIn("missing", html)
        # I quattro campi distinti sono tutti renderizzati
        self.assertIn("Coverage", html)
        self.assertIn("Availability", html)
        self.assertIn("Usabile nello score", html)
        self.assertIn("Implementation", html)
        # Provenienza esplicita
        self.assertIn("scraped", html)
        self.assertIn("missing", html)

    def test_indicator_matrix_empty_returns_empty(self):
        self.assertEqual(render_indicator_matrix({}), "")
        self.assertEqual(render_indicator_matrix(None), "")

    def test_market_cards_shows_manual_badge_for_override(self):
        data = _sample_data()
        data["aaii"] = {
            "bullish": 37.0, "neutral": 25.0, "bearish": 38.0,
            "source": "manual", "origin": "manual", "status": "fresh",
            "fetched_at": "2026-08-14T18:20:00+00:00",
            "note": "Inserito manualmente dal sito AAII",
        }
        html = render_market_cards(data)
        self.assertIn(">manual<", html)
        self.assertIn("Inserito manualmente dal sito AAII", html)

    def test_market_cards_shows_naaim_card_when_present(self):
        data = _sample_data()
        data["naaim"] = {
            "exposure": 48.0, "source": "manual", "origin": "manual",
            "status": "fresh", "fetched_at": "2026-08-14T18:30:00+00:00",
        }
        html = render_market_cards(data)
        self.assertIn("NAAIM Exposure", html)
        self.assertIn("48", html)
        self.assertIn(">manual<", html)

    def test_market_cards_contains_pcr(self):
        data = _sample_data()
        data["pcr"] = {"equity_pcr": 0.63, "trade_date": "2026-08-11",
                       "fetched_at": "2026-08-12T00:00:00+00:00"}
        html = render_market_cards(data)
        self.assertIn("Put/Call Ratio", html)
        self.assertIn("0.63", html)

    def test_pcr_legend_entry(self):
        html = render_legend()
        self.assertIn("Put/Call Ratio", html)
        self.assertIn("0.80", html)

    def test_pcr_semaphore_thresholds(self):
        for value, cls in [(0.63, "greed"), (0.70, "greed"), (0.75, None),
                           (0.80, "fear"), (0.95, "fear"), (None, None)]:
            data = _sample_data()
            data["pcr"] = {"equity_pcr": value}
            html = render_market_cards(data)
            # Isola la card PCR: dal label fino alla chiusura della card
            start = html.find("Equity Put/Call Ratio")
            end = html.find('</div></div>', start)
            pcr_card = html[start:end]
            if cls is None:
                # Neutro o assente → nessun badge semaforo nella card PCR
                self.assertNotIn("sema", pcr_card)
            else:
                self.assertIn(f'class="sema {cls}"', pcr_card)

    def test_market_cards_contains_breadth(self):
        data = _sample_data()
        data["pct_sma"] = {"pct_sma50": 69.0, "pct_sma200": 86.2,
                           "fetched_at": "2026-08-12T00:00:00+00:00",
                           "origin": "manual"}
        html = render_market_cards(data)
        self.assertIn("Breadth di mercato", html)
        self.assertIn("69", html)
        self.assertIn("86.2", html)
        self.assertIn("12 ago 2026", html)

    def test_breadth_legend_entry(self):
        html = render_legend()
        self.assertIn("Breadth di mercato", html)
        self.assertIn("ipervenduto", html)

    def test_breadth_semaphore_thresholds(self):
        cases = [  # (p50, p200, atteso_p50, atteso_p200)
            (10.0, 86.2, "fear", "ok"),
            (30.0, 40.0, "warning", "warning"),
            (69.0, 20.0, "ok", "fear"),
        ]
        for p50, p200, cls50, cls200 in cases:
            data = _sample_data()
            data["pct_sma"] = {"pct_sma50": p50, "pct_sma200": p200}
            html = render_market_cards(data)
            card = html.split("Breadth di mercato")[1]
            self.assertIn(f'class="sema {cls50}"', card)
            self.assertIn(f'class="sema {cls200}"', card)

    def test_market_cards_contains_insider(self):
        data = _sample_data()
        data["insider"] = {"total": {"tickers_with_bonus": 2, "max_bonus": 1.0,
                                     "max_ticker": "NVDA"},
                           "fetched_at": "2026-08-12T00:00:00+00:00"}
        html = render_market_cards(data)
        self.assertIn("Insider", html)
        self.assertIn("2 titoli", html)
        self.assertIn("NVDA", html)

    def test_insider_legend_entry(self):
        html = render_legend()
        self.assertIn("Insider", html)
        self.assertIn("max +1.5", html)

    def test_insider_card_missing_data_no_crash(self):
        # Dati assenti → card renderizzata con "0 titoli" senza eccezioni
        data = _sample_data()
        html = render_market_cards(data)
        self.assertIn("Insider", html)
        self.assertIn("0 titoli", html)

    def test_insider_card_escapes_max_ticker(self):
        data = _sample_data()
        data["insider"] = {"total": {"tickers_with_bonus": 1, "max_bonus": 1.0,
                                     "max_ticker": "<b>x</b>"},
                           "fetched_at": "2026-08-12T00:00:00+00:00"}
        html = render_market_cards(data)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)
        self.assertNotIn("<b>x</b>", html)

    def test_ticker_table_contains_rows(self):
        data = _sample_data()
        # RSI sopra 70 → il badge "overbought" deve comparire
        entries = data["indicators"]["semiconductors"]
        overbought = dict(entries["AMAT"], rsi_14=75.0)
        html = render_ticker_table("semiconductors", {"AMAT": overbought})
        self.assertIn("AMAT", html)
        self.assertIn("75", html)
        self.assertIn("overbought", html)  # classe semaforo presente nel markup

    def test_sema_separates_value_and_badge(self):
        # Valore e badge devono essere in contenitori distinti (sema-cell/sema-val)
        data = _sample_data()
        entries = data["indicators"]["semiconductors"]
        with_badge = dict(entries["AMAT"], drawdown_52w=-20.0)  # critical
        html = render_ticker_table("semiconductors", {"AMAT": with_badge})
        self.assertIn('class="sema-cell"', html)
        self.assertIn('class="sema-val">-20</span>', html)
        self.assertIn('class="sema critical">critical</span>', html)

    def test_legend_contains_indicators_and_toggles(self):
        html = render_legend()
        self.assertIn("Legenda indicatori", html)
        self.assertIn("Indicatori di mercato", html)
        self.assertIn("Indicatori azionari", html)
        # Ogni riga è un <details> espandibile (toggle per-riga)
        self.assertGreaterEqual(html.count("<details"), 9)
        self.assertIn("Fear &amp; Greed", html)
        self.assertIn("RSI", html)
        self.assertIn("Drawdown", html)

    def test_legend_contains_semaphore_explanation(self):
        html = render_legend()
        self.assertIn("Semafori", html)
        self.assertIn("sema-dot", html)
        self.assertIn("overbought", html)
        self.assertIn("critical", html)

    def test_legend_contains_operational_guide(self):
        html = render_legend()
        self.assertIn("Guida operativa", html)
        self.assertIn("Possibile acquisto", html)
        self.assertIn("Possibile vendita", html)
        self.assertIn("Non costituisce consulenza finanziaria", html)

    def test_build_page_contains_legend(self):
        html = build_page(_sample_data())
        self.assertIn("Legenda indicatori", html)
        self.assertIn("Guida operativa", html)

    def test_build_page_contains_all_sections(self):
        html = build_page(_sample_data())
        self.assertIn("Market Dashboard", html)
        self.assertIn("SEMICONDUCTORS", html)
        self.assertIn("Stato sorgenti", html)
        self.assertIn("dark", html)  # classe tema presente
        self.assertIn("localStorage", html)  # toggle JS presente

    def test_build_page_sections_collapsible_and_ordered(self):
        html = build_page(_sample_data())
        # Ogni sezione con H2 è un <details class="section" open> (aperta di default)
        self.assertGreaterEqual(html.count('<details class="section" open>'), 3)
        # Ordine: mercato → ticker → matrice indicatori → legenda
        idx_market = html.find("Indicatori di mercato")
        idx_ticker = html.find("SEMICONDUCTORS")
        idx_matrix = html.find("Stato indicatori strategia")
        idx_legend = html.find("Legenda indicatori")
        self.assertLess(idx_market, idx_ticker)
        self.assertLess(idx_ticker, idx_matrix)
        self.assertLess(idx_matrix, idx_legend)

    def test_build_page_has_global_sections_toggle(self):
        html = build_page(_sample_data())
        self.assertIn('id="sections-toggle"', html)
        self.assertIn("Chiudi tutte", html)  # tutte aperte di default
        self.assertIn("allOpen", html)  # JS del toggle globale presente
        self.assertIn("sections[i].open = open", html)

    def test_build_page_has_nav_menu(self):
        html = build_page(_sample_data())
        self.assertIn('class="page-nav"', html)
        # Tutti i link delle pagine disponibili
        self.assertIn('href="/report.html"', html)
        self.assertIn('href="/overrides.html"', html)
        self.assertIn('href="/tickers.html"', html)
        # La pagina corrente è evidenziata
        self.assertIn('class="nav-link active">📊 Report</a>', html)

    def test_build_page_has_favicon(self):
        html = build_page(_sample_data())
        self.assertIn('rel="icon"', html)
        self.assertIn("data:image/svg+xml", html)

    def test_ticker_table_sortable_filterable_markup(self):
        data = _sample_data()
        entries = data["indicators"]["semiconductors"]
        html = render_ticker_table("semiconductors", entries)
        # Tabella marcata per il JS di sort/filter
        self.assertIn('class="ticker-table"', html)
        # Tipi di colonna dichiarati
        self.assertIn('<th data-type="text">Ticker</th>', html)
        self.assertIn('<th data-type="num">Close</th>', html)
        self.assertIn('<th data-type="date">Aggiornato</th>', html)
        # Valori machine-readable sulle celle
        self.assertIn('data-value="AMAT"', html)
        self.assertIn('data-value="52.08"', html)  # rsi
        # Segnale machine-readable (uno dei tre valori operativi)
        self.assertTrue(
            any(f'data-value="{s}"' in html for s in ("buy", "watchlist", "hold"))
        )

    def test_build_page_has_table_script(self):
        html = build_page(_sample_data())
        # JS di sort/filter presente (filtri a popup da icona sulla testata)
        self.assertIn("table.ticker-table", html)
        self.assertIn("Azzera filtri e ordine", html)
        self.assertIn("filter-icon", html)
        self.assertIn("filter-popup", html)
        self.assertIn("popup-apply", html)
        self.assertIn("popup-clear", html)
        # Niente riga filtri dentro la tabella (le colonne non si allargano)
        self.assertNotIn("filter-row", html)
        # Icona attiva con colore diverso quando c'è un filtro
        self.assertIn('classList.toggle("active"', html)

    def test_legend_has_strategy_explanations(self):
        html = render_legend()
        # Spiegazione semplice buy/osserva/vendi per gli indicatori
        self.assertEqual(html.count("legend-strategy"), 12)
        self.assertIn("In pratica", html)
        self.assertIn("<strong>comprare</strong>", html)

    def test_ticker_sections_ignores_category_status_key(self):
        # La categoria ha una chiave "status" (stringa) che NON è un ticker
        data = _sample_data()
        data["indicators"]["semiconductors"]["status"] = "fresh"
        data["ohlcv"]["semiconductors"]["status"] = "fresh"
        html = build_page(data)
        self.assertIn("SEMICONDUCTORS (1)", html)
        self.assertIn("AMAT", html)

    def test_ticker_sections_ignores_module_status_key(self):
        # Il modulo ha una chiave "status" top-level (stringa) che NON è una categoria
        data = _sample_data()
        data["indicators"]["status"] = "fresh"
        data["ohlcv"]["status"] = "fresh"
        html = build_page(data)
        self.assertIn("SEMICONDUCTORS (1)", html)
        self.assertIn("AMAT", html)

    def test_ticker_sections_ignores_category_status_key_asymmetric(self):
        # "status" esiste solo in una delle due mappe → non deve creare ticker fantasma
        data = _sample_data()
        data["indicators"]["semiconductors"]["status"] = "fresh"
        html = build_page(data)
        self.assertIn("SEMICONDUCTORS (1)", html)
        self.assertNotIn(">status</span>", html)

    def test_ticker_rows_include_age_attrs(self):
        data = _sample_data()
        entries = data["indicators"]["semiconductors"]
        html = render_ticker_table("semiconductors", entries)
        self.assertIn('data-fetched-at="2026-08-12T14:30:06+00:00"', html)
        self.assertIn('data-stale-hours="24"', html)

    def test_ticker_row_without_fetched_at_has_no_attrs(self):
        data = _sample_data()
        entries = data["indicators"]["semiconductors"]
        no_ts = dict(entries["AMAT"], fetched_at=None)
        html = render_ticker_table("semiconductors", {"AMAT": no_ts})
        self.assertNotIn("data-fetched-at=", html)

    def test_ticker_meta_rendered_when_provided(self):
        data = _sample_data()
        entries = data["indicators"]["semiconductors"]
        meta = {"AMAT": {"symbol": "AMAT", "name": "Applied Materials",
                         "quality_tier": "core", "strategy_role": "semiconductor_equipment",
                         "buy_the_dip_validity": "high", "notes": "Rischio geopolitico"}}
        html = render_ticker_table("semiconductors", entries, tickers_meta=meta)
        self.assertIn("ticker-meta", html)
        self.assertIn("core", html)
        self.assertIn("semiconductor_equipment", html)
        self.assertIn("high", html)
        self.assertIn("Rischio geopolitico", html)

    def test_ticker_meta_absent_no_meta_line(self):
        data = _sample_data()
        entries = data["indicators"]["semiconductors"]
        html = render_ticker_table("semiconductors", entries)
        self.assertNotIn("ticker-meta", html)

    def test_ticker_meta_escaped(self):
        data = _sample_data()
        entries = data["indicators"]["semiconductors"]
        meta = {"AMAT": {"symbol": "AMAT", "name": "Applied Materials",
                         "quality_tier": "core", "notes": "<script>alert(1)</script>"}}
        html = render_ticker_table("semiconductors", entries, tickers_meta=meta)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_ticker_meta_ordering_core_first(self):
        data = _sample_data()
        entries = data["indicators"]["semiconductors"]
        # Aggiungo un ticker opportunistico che alfabeticamente verrebbe prima.
        entries["ZZZZ"] = {"symbol": "ZZZZ", "name": "Zeta", "rsi_14": 50.0,
                           "fetched_at": "2026-08-12T14:30:06+00:00",
                           "frequency": "daily", "stale_after_hours": 24, "status": "fresh"}
        meta = {
            "AMAT": {"symbol": "AMAT", "name": "Applied Materials", "quality_tier": "core"},
            "ZZZZ": {"symbol": "ZZZZ", "name": "Zeta", "quality_tier": "opportunistic"},
        }
        html = render_ticker_table("semiconductors", entries, tickers_meta=meta)
        # core (AMAT) deve comparire prima di opportunistic (ZZZZ)
        self.assertLess(html.index("AMAT"), html.index("ZZZZ"))

    def test_ticker_meta_ordering_unknown_tier_last(self):
        data = _sample_data()
        entries = data["indicators"]["semiconductors"]
        entries["ZZZZ"] = {"symbol": "ZZZZ", "name": "Zeta", "rsi_14": 50.0,
                           "fetched_at": "2026-08-12T14:30:06+00:00",
                           "frequency": "daily", "stale_after_hours": 24, "status": "fresh"}
        meta = {
            "AMAT": {"symbol": "AMAT", "name": "Applied Materials", "quality_tier": "core"},
            "ZZZZ": {"symbol": "ZZZZ", "name": "Zeta"},  # nessun tier
        }
        html = render_ticker_table("semiconductors", entries, tickers_meta=meta)
        self.assertLess(html.index("AMAT"), html.index("ZZZZ"))

    def test_build_page_with_tickers_config_renders_meta(self):
        data = _sample_data()
        tickers_config = {
            "semiconductors": [
                {"symbol": "AMAT", "name": "Applied Materials",
                 "quality_tier": "core", "strategy_role": "semiconductor_equipment",
                 "buy_the_dip_validity": "high"}
            ]
        }
        html = build_page(data, tickers_config)
        self.assertIn("ticker-meta", html)
        self.assertIn("semiconductor_equipment", html)

    def test_build_page_without_tickers_config_no_meta(self):
        html = build_page(_sample_data())
        # La classe CSS .ticker-meta è sempre presente nello <style>;
        # verifichiamo che NON ci sia alcuna riga metadata nel corpo.
        self.assertNotIn("class='ticker-meta'", html)

    def test_metadata_never_bypasses_fgi_gate(self):
        # Anche con metadata "core/high", un FGI non-fresh (fail-closed) NON
        # produce un segnale di acquisto: il gate FGI resta l'unico gate.
        data = _sample_data()
        data["fgi"] = {"score": 62.65, "zone": "greed",
                       "fetched_at": "2026-08-12T14:29:42+00:00",
                       "frequency": "daily", "stale_after_hours": 24,
                       "status": "stale"}  # stale → gate fail-closed
        tickers_config = {
            "semiconductors": [
                {"symbol": "AMAT", "name": "Applied Materials",
                 "quality_tier": "core", "buy_the_dip_validity": "high"}
            ]
        }
        html = build_page(data, tickers_config)
        self.assertIn("class='ticker-meta'", html)  # metadata mostrati...
        # ...ma mai come segnale: nessun badge "signal buy" (VALUTA INGRESSO).
        # NB: "VALUTA INGRESSO" compare nella legenda, quindi verifichiamo il badge.
        self.assertNotIn('class="signal buy"', html)
        self.assertIn('class="signal hold"', html)


class TestAgeAttrs(unittest.TestCase):
    def test_returns_attrs_with_valid_timestamp(self):
        attrs = _age_attrs("2026-08-12T14:30:06+00:00", 24)
        self.assertIn('data-fetched-at="2026-08-12T14:30:06+00:00"', attrs)
        self.assertIn('data-stale-hours="24"', attrs)

    def test_returns_empty_without_fetched_at(self):
        self.assertEqual(_age_attrs(None, 24), "")
        self.assertEqual(_age_attrs("", 24), "")

    def test_returns_empty_without_stale_hours(self):
        self.assertEqual(_age_attrs("2026-08-12T14:30:06+00:00", None), "")

    def test_escapes_iso_value(self):
        attrs = _age_attrs('2026-08-12T14:30:06+00:00" onclick="x', 24)
        self.assertNotIn('" onclick="', attrs)


class TestAgeScript(unittest.TestCase):
    def test_script_contains_age_logic(self):
        from report_html import _SCRIPT
        self.assertIn("data-fetched-at", _SCRIPT)
        self.assertIn("data-stale-hours", _SCRIPT)
        self.assertIn("scaduto da", _SCRIPT)
        self.assertIn("aggiornato", _SCRIPT)
        self.assertIn("age-badge", _SCRIPT)

    def test_css_contains_age_class(self):
        from report_html import _CSS
        self.assertIn(".age", _CSS)


class TestRender(unittest.TestCase):
    def test_render_writes_html_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/config.yaml"
            data_path = f"{tmp}/output.json"
            with open(config_path, "w", encoding="utf-8") as fh:
                fh.write(
                    "output:\n"
                    f"  json_path: {data_path}\n"
                    "  db_path: output/audit.db\n"
                    "scrapers:\n"
                    "  fgi:\n"
                    "    module: scrapers.fgi_scraper\n"
                    "    output_key: fgi\n"
                    "    schedule: daily\n"
                )
            with open(data_path, "w", encoding="utf-8") as fh:
                json.dump(_sample_data(), fh)
            html_path = render(config_path, output_path=f"{tmp}/report.html")
            self.assertTrue(Path(html_path).exists())
            content = Path(html_path).read_text(encoding="utf-8")
            self.assertIn("Market Dashboard", content)

    def test_page_links_to_overrides_page(self):
        html = build_page(_sample_data())
        self.assertIn("Immissione manuale", html)
        self.assertIn("/overrides.html", html)

    def test_render_missing_output_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = f"{tmp}/config.yaml"
            with open(config_path, "w", encoding="utf-8") as fh:
                fh.write(
                    "output:\n"
                    f"  json_path: {tmp}/nonexistent.json\n"
                    "  db_path: output/audit.db\n"
                    "scrapers:\n"
                    "  fgi:\n"
                    "    module: scrapers.fgi_scraper\n"
                    "    output_key: fgi\n"
                    "    schedule: daily\n"
                )
            with self.assertRaises(FileNotFoundError):
                render(config_path)


if __name__ == "__main__":
    unittest.main()
