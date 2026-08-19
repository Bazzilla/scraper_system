"""Load and validate the scraper-system config.yaml.

Config defines "who" (scrapers to run), "when" (schedule/frequency),
and "where" (output paths). Pure functions with explicit path injection.
"""

from __future__ import annotations

from typing import Any

import yaml

REQUIRED_TOP_LEVEL = ("scrapers",)
REQUIRED_SCRAPER_FIELDS = ("module", "output_key", "schedule")
VALID_SCHEDULES = ("daily", "weekly")

# Strategic ticker classification (display-only, never used as a BUY signal).
QUALITY_TIERS = ("core", "secondary", "opportunistic")
VALIDITY_LEVELS = ("high", "medium", "low")
STRATEGY_ROLES = (
    "compounder",
    "cyclical_leader",
    "turnaround",
    "defense_resilient",
    "valuation_sensitive",
    "semiconductor_equipment",
    "foundry",
    "analog_industrial",
    "memory",
    "defense_prime",
    "aerospace_components",
    "defense_tech",
)


def load_config(path: str) -> dict[str, Any]:
    """Load and validate the YAML config from the given path."""
    with open(path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    return validate_config(config)


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate the config structure, raising descriptive errors."""
    if not isinstance(config, dict):
        raise ValueError("Config must be a mapping")

    for key in REQUIRED_TOP_LEVEL:
        if key not in config:
            raise ValueError(f"Config missing required top-level key: {key!r}")

    scrapers = config["scrapers"]
    if not isinstance(scrapers, dict) or not scrapers:
        raise ValueError("Config 'scrapers' must be a non-empty mapping")

    for name, scraper in scrapers.items():
        _validate_scraper(name, scraper)

    if "tickers" in config:
        # Normalizza la sezione ticker (lista semplice → metadata arricchiti)
        # e valida i metadata strategici. Il config ritornato ha forma canonica.
        config["tickers"] = normalize_tickers(config["tickers"])

    if "scheduler" in config:
        _validate_scheduler(config["scheduler"])

    return config


def _validate_scheduler(scheduler: Any) -> None:
    """Validate the optional 'scheduler' section (interval/run_at/weekday)."""
    if not isinstance(scheduler, dict):
        raise ValueError("Config 'scheduler' must be a mapping")

    interval = scheduler.get("interval", "daily")
    if interval not in ("daily", "weekly"):
        raise ValueError(
            f"Scheduler 'interval' must be daily|weekly, got {interval!r}"
        )

    run_at = scheduler.get("run_at", "00:00")
    if not isinstance(run_at, str):
        raise ValueError("Scheduler 'run_at' must be a string 'HH:MM'")
    try:
        hour, minute = (int(part) for part in run_at.split(":"))
    except ValueError as error:
        raise ValueError(
            f"Scheduler 'run_at' must be 'HH:MM', got {run_at!r}"
        ) from error
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Scheduler 'run_at' out of range: {run_at!r}")

    if "weekday" in scheduler:
        weekday = scheduler["weekday"]
        if not isinstance(weekday, int) or not (0 <= weekday <= 6):
            raise ValueError("Scheduler 'weekday' must be an integer 0-6")


def _validate_scraper(name: str, scraper: Any) -> None:
    if not isinstance(scraper, dict):
        raise ValueError(f"Scraper {name!r} must be a mapping")

    for field in REQUIRED_SCRAPER_FIELDS:
        if field not in scraper:
            raise ValueError(f"Scraper {name!r} missing required field: {field!r}")

    schedule = scraper["schedule"]
    if schedule not in VALID_SCHEDULES:
        raise ValueError(
            f"Scraper {name!r} has invalid schedule {schedule!r}; "
            f"expected one of {VALID_SCHEDULES}"
        )


def normalize_tickers(tickers: Any) -> dict[str, Any]:
    """Normalize the ``tickers`` section into a canonical shape.

    Supports two input formats (backward compatible):
    - legacy simple list:  {"semiconductors": ["AMAT", "LRCX"]}
    - enriched metadata:   {"semiconductors": [{"symbol": "AMAT",
                                                "name": "Applied Materials",
                                                "quality_tier": "core", ...}]}

    Returns the same mapping with every entry as ``{symbol, name, ...meta}``.
    Entries given as plain strings become ``{symbol: <s>, name: <s>}``.
    """
    if not isinstance(tickers, dict):
        raise ValueError("Config 'tickers' must be a mapping")

    normalized: dict[str, Any] = {}
    for category, entries in tickers.items():
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"Ticker category {category!r} must be a non-empty list")
        normalized_entries: list[dict[str, Any]] = []
        for entry in entries:
            if isinstance(entry, str):
                entry = {"symbol": entry, "name": entry}
            if not isinstance(entry, dict):
                raise ValueError(f"Ticker entry in category {category!r} must be a mapping or string")
            for field in ("symbol", "name"):
                if field not in entry:
                    raise ValueError(
                        f"Ticker entry in category {category!r} "
                        f"missing required field: {field!r}"
                    )
            symbol = entry["symbol"]
            name = entry["name"]
            if not isinstance(name, str):
                raise ValueError(f"Ticker 'name' for symbol {symbol!r} must be a string")
            if not isinstance(symbol, str) or not symbol.strip():
                raise ValueError("Ticker 'symbol' must be a non-empty string")
            normalized_entries.append(dict(entry))
        normalized[category] = normalized_entries

    _validate_tickers_metadata(normalized)
    return normalized


def _validate_tickers_metadata(tickers: dict[str, Any]) -> None:
    """Validate optional strategic metadata. Display-only, never a BUY signal."""
    seen_symbols: set[str] = set()
    for category, entries in tickers.items():
        for entry in entries:
            symbol = entry["symbol"].strip()
            if symbol in seen_symbols:
                raise ValueError(f"Duplicate ticker symbol: {symbol!r}")
            seen_symbols.add(symbol)

            tier = entry.get("quality_tier")
            if tier is not None and tier not in QUALITY_TIERS:
                raise ValueError(
                    f"Invalid quality_tier {tier!r} for {symbol!r}; "
                    f"expected one of {QUALITY_TIERS}"
                )
            validity = entry.get("buy_the_dip_validity")
            if validity is not None and validity not in VALIDITY_LEVELS:
                raise ValueError(
                    f"Invalid buy_the_dip_validity {validity!r} for {symbol!r}; "
                    f"expected one of {VALIDITY_LEVELS}"
                )
            role = entry.get("strategy_role")
            if role is not None and role not in STRATEGY_ROLES:
                raise ValueError(
                    f"Invalid strategy_role {role!r} for {symbol!r}; "
                    f"expected one of {STRATEGY_ROLES}"
                )
            notes = entry.get("notes")
            if notes is not None and not isinstance(notes, str):
                raise ValueError(f"Ticker 'notes' for symbol {symbol!r} must be a string")


def _validate_tickers(tickers: Any) -> None:
    """Validate the optional 'tickers' section (category -> list of {symbol, name})."""
    if not isinstance(tickers, dict):
        raise ValueError("Config 'tickers' must be a mapping")

    seen_symbols: set[str] = set()
    for category, entries in tickers.items():
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"Ticker category {category!r} must be a non-empty list")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"Ticker entry in category {category!r} must be a mapping")
            for field in ("symbol", "name"):
                if field not in entry:
                    raise ValueError(
                        f"Ticker entry in category {category!r} "
                        f"missing required field: {field!r}"
                    )
            symbol = entry["symbol"]
            name = entry["name"]
            if not isinstance(name, str):
                raise ValueError(
                    f"Ticker 'name' for symbol {symbol!r} must be a string"
                )
            if not isinstance(symbol, str) or not symbol.strip():
                raise ValueError("Ticker 'symbol' must be a non-empty string")
            symbol = symbol.strip()
            if symbol in seen_symbols:
                raise ValueError(f"Duplicate ticker symbol: {symbol!r}")
            seen_symbols.add(symbol)