"""Main orchestrator for scraper-system.

Flow: load config -> run scrapers in sequence -> consolidate -> audit -> save.
A failure in one scraper does not block the others.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audit import init_db, record_execution
from config_loader import load_config
from consolidator import consolidate
from indicator_registry import (
    build_availability,
    load_registry,
    normalize_registry,
    summarize,
)
from manual_overrides import apply_overrides, load_validated_overrides
from registry import get_scraper

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _run_scraper_safely(
    name: str,
    scraper: dict[str, Any],
    base_dir: Path,
    tickers: dict[str, Any],
) -> tuple[dict[str, Any] | None, str, str | None]:
    """Run one scraper, returning (result, status, error).

    Injects the top-level ``tickers`` section and resolves ``cache_path`` /
    ``history_path`` (relative to the project root) into the scraper config.
    """
    scraper_config = dict(scraper.get("config", {}))
    scraper_config["tickers"] = tickers
    try:
        for path_key in ("cache_path", "history_path"):
            if path_key in scraper_config:
                path_value = scraper_config[path_key]
                if not isinstance(path_value, str):
                    raise TypeError(
                        f"{path_key} must be a string, got {type(path_value).__name__}"
                    )
                scraper_config[path_key] = str(base_dir / path_value)
        run = get_scraper(scraper["module"])
        result = run(scraper_config)
        return result, "success", None
    except Exception as error:  # noqa: BLE001 - isolate per-module failures
        logger.error("Scraper %s failed: %s", name, error)
        return None, "error", str(error)


def run(
    config_path: str,
    output_path: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Execute the full orchestration flow.

    Args:
        config_path: Path to config.yaml.
        output_path: Path where the consolidated JSON is written. Defaults to
            the value in config.yaml (``output.json_path``).
        db_path: Path to the SQLite audit database. Defaults to the value in
            config.yaml (``output.db_path``).
    """
    config = load_config(config_path)
    output_cfg = config.get("output", {})
    output_path = output_path or output_cfg.get("json_path", "output/output.json")
    db_path = db_path or output_cfg.get("db_path", "output/scraper_audit.db")

    # Resolve relative paths against the config file's directory (project root).
    base_dir = Path(config_path).resolve().parent
    output_path = str(base_dir / output_path)
    db_path = str(base_dir / db_path)

    # Ensure parent directories exist before writing output files.
    for path in (output_path, db_path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {}

    with sqlite3.connect(db_path) as conn:
        init_db(conn)
    for name, scraper in config["scrapers"].items():
        logger.info("▶ [%s] start", name)
        start = time.monotonic()
        result, status, error = _run_scraper_safely(
            name, scraper, base_dir, config.get("tickers", {})
        )
        elapsed = time.monotonic() - start
        record_execution(conn, name, _now_iso(), status, error)
        if result is not None:
            # Il risultato scrapato è esplicitamente marcato (mai confuso
            # con un manual override).
            result["origin"] = "scraped"
            results[scraper["output_key"]] = result
            logger.info("✓ [%s] done — success (%.1fs)", name, elapsed)
        else:
            # Fail-closed: un modulo fallito NON sparisce dall'output.
            # Viene registrato con status "error" così il consolidator e
            # il report lo segnalano invece di fingere che non esista.
            results[scraper["output_key"]] = {
                "status": "error",
                "origin": "missing",
                "error": error or "unknown error",
                "fetched_at": _now_iso(),
            }
            logger.error("✗ [%s] failed — %s (%.1fs)", name, error, elapsed)

    # Manual overrides: priorità scraping > manual > missing. Gli override
    # validi e freschi sostituiscono i risultati error/missing (o quelli fresh
    # solo se esplicitamente forzati in strategy.force_manual_overrides).
    results = _apply_manual_overrides(config, base_dir, results)

    output = consolidate(results)
    output["strategy_indicators"] = _build_strategy_indicators(config, base_dir, results)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)

    return output


def _apply_manual_overrides(
    config: dict[str, Any],
    base_dir: Path,
    results: dict[str, Any],
) -> dict[str, Any]:
    """Load, validate and apply manual overrides to the results.

    Fail-closed: malformed overrides are logged and ignored; expired overrides
    become stale (never usable in scoring); scraping wins by default unless the
    key is in ``strategy.force_manual_overrides``.
    """
    strategy_cfg = config.get("strategy", {})
    overrides_path = strategy_cfg.get("manual_overrides", "manual_overrides.yaml")
    force_keys = strategy_cfg.get("force_manual_overrides", []) or []
    resolved = base_dir / overrides_path
    overrides, errors = load_validated_overrides(str(resolved))
    for error in errors:
        logger.warning("Manual override ignored: %s", error)
    return apply_overrides(results, overrides, force_keys=force_keys)


def _build_strategy_indicators(
    config: dict[str, Any],
    base_dir: Path,
    results: dict[str, Any],
) -> dict[str, Any]:
    """Build the strategy-indicator coverage summary.

    Combines the machine-readable registry (coverage + implementation_status,
    both static) with the latest run's module statuses (availability, dynamic)
    and the config's ``strategy.proxy_accepted`` list. Fail-closed:

    - coverage (statico): l'indicatore APPARTIENE alla strategia (dalle
      specifiche) — non dipende dal runtime, resta true anche se missing.
    - implementation_status (statico): implemented / proxy / missing /
      manual_supported.
    - availability: il modulo ha prodotto status "fresh" nell'ultima esecuzione
      (o un manual override valido e fresco).
    - usable_in_strategy_score: coverage E disponibile E implementabile
      (implemented/manual_supported), oppure proxy esplicitamente accettato E
      disponibile.

    The registry path is resolved against the config directory; if the file is
    not there (e.g. a minimal test config), it falls back to the project root.
    """
    strategy_cfg = config.get("strategy", {})
    registry_path = strategy_cfg.get("indicator_registry", "indicator_registry.yaml")
    proxy_accepted = strategy_cfg.get("proxy_accepted", []) or []
    resolved = base_dir / registry_path
    if not resolved.exists():
        resolved = Path(__file__).resolve().parent.parent / registry_path

    raw = load_registry(str(resolved))
    registry = normalize_registry(raw)

    runtime_status: dict[str, str] = {}
    for output_key, value in results.items():
        if isinstance(value, dict) and "status" in value:
            runtime_status[output_key] = str(value["status"])

    availability = build_availability(registry, runtime_status)
    summary = summarize(registry, proxy_accepted, availability)

    # Arricchisci la matrice con la provenienza runtime: scraped | manual | missing
    for key, entry in summary.items():
        if not isinstance(entry, dict) or key in ("_meta", "summary"):
            continue
        output_key = entry.get("output_key")
        if output_key is None:
            entry["source"] = "missing"
        else:
            value = results.get(output_key)
            if isinstance(value, dict) and value.get("origin") == "manual":
                entry["source"] = "manual"
            elif isinstance(value, dict) and value.get("status") == "fresh":
                entry["source"] = "scraped"
            elif isinstance(value, dict) and value.get("status") == "error":
                entry["source"] = "missing"
            else:
                entry["source"] = "missing"
    return summary