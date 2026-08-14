"""Unit tests for the static HTML report generator (pure functions)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from report_html import (
    build_page,
    compute_signal,
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
        self.assertEqual(compute_signal(entry), "buy")

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
        self.assertIn("WATCHLIST", html)

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
        self.assertEqual(compute_signal(entry, "neutral"), "buy")
        self.assertEqual(compute_signal(entry, "greed"), "hold")

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
        self.assertEqual(compute_signal(entry_buy, "fear"), "buy")
        self.assertEqual(compute_signal(entry_weak, "greed"), "watchlist")

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
            compute_signal(entry, "neutral", proxy_accepted={"vix_spot"}),
            compute_signal(entry, "neutral"),
        )

    def test_table_uses_market_regime(self):
        data = _sample_data()
        data["fgi"]["score"] = 70.0  # greed
        entries = data["indicators"]["semiconductors"]
        # Titolo tecnicamente forte → in greed NON deve comparire COMPRA
        strong = dict(entries["AMAT"], rsi_14=50.0, mfi_14=50.0,
                      last_close=560.0, sma_50=500.0, sma_200=400.0,
                      drawdown_52w=-1.0)
        html = render_ticker_table("semiconductors", {"AMAT": strong}, regime="greed")
        self.assertIn("ATTENDI", html)
        self.assertNotIn("COMPRA", html)

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


class TestRenderSections(unittest.TestCase):
    def test_market_cards_contains_values(self):
        html = render_market_cards(_sample_data())
        self.assertIn("Fear &amp; Greed", html)
        self.assertIn("62.65", html)
        self.assertIn("15.28", html)
        self.assertIn("37", html)

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
        data["pct_sma"] = {"total": {"pct_sma50": 69.0, "pct_sma200": 86.2},
                           "fetched_at": "2026-08-12T00:00:00+00:00"}
        html = render_market_cards(data)
        self.assertIn("Breadth settoriale", html)
        self.assertIn("69", html)
        self.assertIn("86.2", html)
        self.assertIn("12 ago 2026", html)

    def test_breadth_legend_entry(self):
        html = render_legend()
        self.assertIn("Breadth settoriale", html)
        self.assertIn("ipervenduto", html)

    def test_breadth_semaphore_thresholds(self):
        cases = [  # (p50, p200, atteso_p50, atteso_p200)
            (10.0, 86.2, "fear", "ok"),
            (30.0, 40.0, "warning", "warning"),
            (69.0, 20.0, "ok", "fear"),
        ]
        for p50, p200, cls50, cls200 in cases:
            data = _sample_data()
            data["pct_sma"] = {"total": {"pct_sma50": p50, "pct_sma200": p200}}
            html = render_market_cards(data)
            card = html.split("Breadth settoriale")[1]
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
