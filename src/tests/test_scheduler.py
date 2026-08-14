"""Unit tests for the scheduler (pure planning logic + run loop)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest import mock

from scheduler import (
    interval_seconds,
    next_run,
    parse_run_at,
    run_once,
    seconds_until,
)

TZ = timezone.utc


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


class TestIntervalSeconds(unittest.TestCase):
    def test_daily(self):
        self.assertEqual(interval_seconds("daily"), 86400)

    def test_weekly(self):
        self.assertEqual(interval_seconds("weekly"), 7 * 86400)

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            interval_seconds("monthly")


class TestParseRunAt(unittest.TestCase):
    def test_parses_valid(self):
        self.assertEqual(parse_run_at("08:30"), (8, 30))
        self.assertEqual(parse_run_at("00:00"), (0, 0))
        self.assertEqual(parse_run_at("23:59"), (23, 59))

    def test_invalid_format_raises(self):
        for bad in ("0830", "08:60", "24:00", "abc", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_run_at(bad)

    def test_single_digit_hour_accepted(self):
        # "8:30" è un formato valido (ora singola cifra)
        self.assertEqual(parse_run_at("8:30"), (8, 30))


class TestNextRun(unittest.TestCase):
    def test_daily_before_run_at_same_day(self):
        now = _dt("2026-08-14T06:00:00+00:00")
        self.assertEqual(next_run("daily", now, run_at="08:00"), _dt("2026-08-14T08:00:00+00:00"))

    def test_daily_after_run_at_next_day(self):
        now = _dt("2026-08-14T09:00:00+00:00")
        self.assertEqual(next_run("daily", now, run_at="08:00"), _dt("2026-08-15T08:00:00+00:00"))

    def test_daily_at_exact_time_next_day(self):
        now = _dt("2026-08-14T08:00:00+00:00")
        self.assertEqual(next_run("daily", now, run_at="08:00"), _dt("2026-08-15T08:00:00+00:00"))

    def test_weekly_same_day_before_run_at(self):
        # 2026-08-14 è un venerdì (weekday 4). Prossimo lunedì (weekday 0).
        now = _dt("2026-08-14T06:00:00+00:00")
        self.assertEqual(next_run("weekly", now, run_at="08:00", weekday=0), _dt("2026-08-17T08:00:00+00:00"))

    def test_weekly_later_same_week(self):
        # lunedì (0) → mercoledì (2) stessa settimana
        now = _dt("2026-08-10T09:00:00+00:00")  # lunedì
        self.assertEqual(next_run("weekly", now, run_at="08:00", weekday=2), _dt("2026-08-12T08:00:00+00:00"))

    def test_weekly_past_weekday_rolls_next_week(self):
        # mercoledì (2) → lunedì (0) prossima settimana
        now = _dt("2026-08-12T09:00:00+00:00")  # mercoledì
        self.assertEqual(next_run("weekly", now, run_at="08:00", weekday=0), _dt("2026-08-17T08:00:00+00:00"))

    def test_weekly_exact_time_rolls_next_week(self):
        now = _dt("2026-08-17T08:00:00+00:00")  # lunedì alle 08:00
        self.assertEqual(next_run("weekly", now, run_at="08:00", weekday=0), _dt("2026-08-24T08:00:00+00:00"))

    def test_invalid_interval_raises(self):
        with self.assertRaises(ValueError):
            next_run("monthly", _dt("2026-08-14T06:00:00+00:00"))


class TestSecondsUntil(unittest.TestCase):
    def test_positive(self):
        target = _dt("2026-08-14T08:00:00+00:00")
        now = _dt("2026-08-14T07:00:00+00:00")
        self.assertEqual(seconds_until(target, now), 3600.0)

    def test_clamps_negative_to_zero(self):
        target = _dt("2026-08-14T06:00:00+00:00")
        now = _dt("2026-08-14T07:00:00+00:00")
        self.assertEqual(seconds_until(target, now), 0.0)


class TestRunOnce(unittest.TestCase):
    def test_calls_orchestrator(self):
        run_fn = mock.Mock(return_value={"ok": True})
        result = run_once("../config.yaml", run_fn=run_fn)
        self.assertEqual(result, {"ok": True})
        run_fn.assert_called_once_with("../config.yaml", None, None)

    def test_forwards_output_and_db(self):
        run_fn = mock.Mock(return_value={})
        run_once("../config.yaml", output_path="/tmp/out.json", db_path="/tmp/db.db", run_fn=run_fn)
        run_fn.assert_called_once_with("../config.yaml", "/tmp/out.json", "/tmp/db.db")


class TestRunLoop(unittest.TestCase):
    def test_loop_sleeps_until_next_run_then_executes(self):
        # Config daily run_at=08:00, now=06:00 → sleep 2h poi esegue.
        import tempfile
        from pathlib import Path

        run_fn = mock.Mock(return_value={})
        sleep_calls: list[float] = []
        now_values = [
            _dt("2026-08-14T06:00:00+00:00"),  # prima iterazione: calcola next
            _dt("2026-08-14T08:00:00+00:00"),  # dopo il sleep: esegue e calcola di nuovo
            _dt("2026-08-14T09:00:00+00:00"),  # seconda iterazione
        ]
        now_iter = iter(now_values)

        def fake_now() -> datetime:
            return next(now_iter)

        def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            # Ferma il loop dopo la prima attesa (prima esecuzione avvenuta)
            if len(sleep_calls) >= 2:
                raise StopIteration

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.yaml"
            cfg.write_text(
                "scrapers: {}\n"
                "scheduler:\n"
                "  interval: daily\n"
                "  run_at: \"08:00\"\n"
            )
            from scheduler import run_loop
            # Limita il loop a 2 iterazioni lanciando StopIteration dal sleep
            with self.assertRaises(StopIteration):
                run_loop(str(cfg), run_fn=run_fn, sleep_fn=fake_sleep, now_fn=fake_now)
        self.assertEqual(run_fn.call_count, 1)
        self.assertTrue(all(s >= 0 for s in sleep_calls))
        # prima attesa = 2h (7200s)
        self.assertGreaterEqual(sleep_calls[0], 7200.0)


if __name__ == "__main__":
    unittest.main()
