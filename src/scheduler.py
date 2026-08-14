"""Scheduler for scraper-system.

Executes the orchestrator (``orchestrator.run``) on an interval derived from
the ``scheduler`` section of config.yaml:

    scheduler:
      interval: daily | weekly      # required
      run_at: "HH:MM"               # optional, default "00:00"
      weekday: 0-6                  # optional (weekly only), default 0 (lun)

Pure functions (``next_run``, ``interval_seconds``) are unit-testable without
network; ``run_loop`` is the long-running entry point; ``main`` provides a CLI:

    cd src && ../.venv/bin/python scheduler.py            # loop
    cd src && ../.venv/bin/python scheduler.py --once     # single run now

The scheduler only decides WHEN to run; it always runs the full orchestration
(``orchestrator.run``), which internally handles per-scraper failures and the
``schedule`` field of each scraper is informational (the orchestrator executes
every configured scraper on every run).
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)

DEFAULT_RUN_AT = "00:00"
DEFAULT_WEEKDAY = 0  # Monday
VALID_INTERVALS = ("daily", "weekly")


def interval_seconds(interval: str) -> int:
    """Return the number of seconds in one interval.

    Raises:
        ValueError: If the interval is not daily/weekly.
    """
    if interval == "daily":
        return 24 * 3600
    if interval == "weekly":
        return 7 * 24 * 3600
    raise ValueError(f"Invalid interval: {interval!r}; expected daily|weekly")


def parse_run_at(run_at: str) -> tuple[int, int]:
    """Parse "HH:MM" into (hour, minute).

    Raises:
        ValueError: If the string is not a valid HH:MM time.
    """
    try:
        hour, minute = (int(part) for part in run_at.split(":"))
    except ValueError as error:
        raise ValueError(
            f"run_at must be 'HH:MM', got {run_at!r}"
        ) from error
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"run_at out of range: {run_at!r}")
    return hour, minute


def next_run(
    interval: str,
    now: datetime,
    run_at: str = DEFAULT_RUN_AT,
    weekday: int = DEFAULT_WEEKDAY,
) -> datetime:
    """Return the next execution datetime on/after ``now``.

    Pure function (no clock access). For daily: the next day at ``run_at``
    (today if the time has not passed yet). For weekly: the next ``weekday``
    at ``run_at``.

    Raises:
        ValueError: If the interval is invalid or run_at is malformed.
    """
    hour, minute = parse_run_at(run_at)
    if interval not in VALID_INTERVALS:
        raise ValueError(f"Invalid interval: {interval!r}; expected daily|weekly")

    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if interval == "daily":
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    # weekly: align to the desired weekday
    days_ahead = (weekday - candidate.weekday()) % 7
    candidate += timedelta(days=days_ahead)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def seconds_until(target: datetime, now: datetime | None = None) -> float:
    """Seconds from now to ``target`` (>= 0)."""
    now = now or datetime.now(timezone.utc)
    delta = target - now
    return max(0.0, delta.total_seconds())


def run_once(
    config_path: str,
    output_path: str | None = None,
    db_path: str | None = None,
    run_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run the orchestrator a single time.

    Args:
        config_path: Path to config.yaml.
        output_path / db_path: Optional overrides passed to the orchestrator.
        run_fn: The orchestrator callable. Injectable for tests; defaults to
            ``orchestrator.run``.

    Returns:
        The consolidated output dict.
    """
    if run_fn is None:
        from orchestrator import run as run_fn

    logger.info("Scheduler: running orchestrator with %s", config_path)
    return run_fn(config_path, output_path, db_path)


def _load_scheduler_config(config_path: str) -> dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}
    return config.get("scheduler", {}) or {}


def run_loop(
    config_path: str,
    output_path: str | None = None,
    db_path: str | None = None,
    run_fn: Callable[..., Any] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    now_fn: Callable[[], datetime] | None = None,
) -> None:
    """Long-running loop: run at every scheduled interval.

    Args:
        config_path: Path to config.yaml (for the ``scheduler`` section).
        output_path / db_path: Optional overrides passed to the orchestrator.
        run_fn: Orchestrator callable (injectable for tests).
        sleep_fn: Sleep callable (injectable for tests).
        now_fn: Clock callable returning an aware datetime (injectable for tests).
    """
    sched = _load_scheduler_config(config_path)
    interval = sched.get("interval", "daily")
    run_at = sched.get("run_at", DEFAULT_RUN_AT)
    weekday = int(sched.get("weekday", DEFAULT_WEEKDAY))
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    logger.info(
        "Scheduler: interval=%s run_at=%s weekday=%s", interval, run_at, weekday
    )

    while True:
        now = now_fn()
        target = next_run(interval, now, run_at=run_at, weekday=weekday)
        wait = seconds_until(target, now)
        logger.info("Next run at %s (in %.0fs)", target.isoformat(), wait)
        sleep_fn(wait)
        run_once(config_path, output_path, db_path, run_fn=run_fn)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="scraper-system scheduler")
    parser.add_argument("--config", default="../config.yaml", help="Path to config.yaml")
    parser.add_argument(
        "--once", action="store_true", help="Run a single execution now and exit"
    )
    parser.add_argument(
        "--output", default=None, help="Override output JSON path"
    )
    parser.add_argument(
        "--db", default=None, help="Override audit SQLite path"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    if args.once:
        run_once(args.config, args.output, args.db)
    else:
        run_loop(args.config, args.output, args.db)


if __name__ == "__main__":
    main()
