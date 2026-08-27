"""Run scraper-system in one shot.

Modes:

    ./.venv/bin/python run.py                # full: orchestration + HTML report
    ./.venv/bin/python run.py --report-only  # HTML report from existing output.json only
    ./.venv/bin/python run.py --override-only  # apply manual overrides to output.json,
                                               # rebuild the indicator matrix and render HTML
                                               # (no scraping)
    ./.venv/bin/python run.py --category semiconductors  # scrape only one category
    ./.venv/bin/python run.py --ticker NVDA              # scrape only one ticker

Merge mode (--category or --ticker + --merge):

    When scraping a single category or ticker, --merge preserves the existing
    output.json data for all other tickers/categories.  Without --merge the
    single scrape would overwrite the entire output, losing previous results.

The script works from any directory: it resolves paths relative to the
project root (the directory containing this file). The config path is
optional and defaults to ``config.yaml``.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Make src/ importable regardless of the current working directory.
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))


def _load_config(config_path: str) -> dict[str, Any]:
    from config_loader import load_config

    return load_config(config_path)


def _resolve(config: dict[str, Any], base_dir: Path, key: str, default: str) -> Path:
    value = config.get("output", {}).get(key, default)
    return base_dir / value


def _render_report(config_path: str) -> str:
    from report_html import render

    print("[report] Rendering HTML report ...")
    path = render(config_path)
    print(f"         report: {path}")
    return path


# ── Merge helpers (used by --category / --ticker to preserve other data) ──

def _deep_merge(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge *new* into *old* — nested dicts are merged recursively."""
    merged = dict(old)
    for key, new_val in new.items():
        old_val = merged.get(key)
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            merged[key] = _deep_merge(old_val, new_val)
        else:
            merged[key] = new_val
    return merged


def _merge_output(old: dict[str, Any], new: dict[str, Any],
                  config_path: str) -> dict[str, Any]:
    """Merge new scrape results into existing output, preserving other data.

    Strategy: only successful results (status != "error") are merged in.
    Error results from the new run are skipped so previous data is kept.
    ``strategy_indicators`` is rebuilt from the merged results.
    """
    old_results: dict[str, Any] = {}
    for key, value in old.items():
        if key not in ("generated_at", "stale_summary", "strategy_indicators"):
            old_results[key] = value

    new_results: dict[str, Any] = {}
    for key, value in new.items():
        if key not in ("generated_at", "stale_summary", "strategy_indicators"):
            new_results[key] = value

    merged = dict(old_results)
    for key, new_val in new_results.items():
        if isinstance(new_val, dict) and new_val.get("status") == "error":
            # Skip errors — keep previous data for this scraper.
            continue
        old_val = merged.get(key)
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            merged[key] = _deep_merge(old_val, new_val)
        else:
            merged[key] = new_val

    config = _load_config(config_path)
    base_dir = Path(config_path).resolve().parent
    from orchestrator import _build_strategy_indicators

    output = new.copy()
    output.update(merged)
    output["generated_at"] = new.get("generated_at", old.get("generated_at"))
    output["strategy_indicators"] = _build_strategy_indicators(config, base_dir, merged)
    return output


def _filter_tickers(
    config: dict[str, Any], category: str | None, ticker: str | None
) -> dict[str, Any]:
    """Return a shallow copy of *config* with tickers filtered by category or symbol."""
    if not category and not ticker:
        return config
    tickers = config.get("tickers", {})
    filtered: dict[str, Any] = dict(config)
    if category:
        if category not in tickers:
            raise ValueError(f"Category not found: {category}")
        filtered["tickers"] = {category: tickers[category]}
    elif ticker:
        upper = ticker.upper()
        for cat, entries in tickers.items():
            for entry in entries:
                if entry.get("symbol", "").upper() == upper:
                    filtered["tickers"] = {cat: [entry]}
                    return filtered
        raise ValueError(f"Ticker not found: {ticker}")
    return filtered


def mode_full(
    config_path: str,
    category: str | None = None,
    ticker: str | None = None,
    merge: bool = False,
) -> int:
    from orchestrator import run as run_orchestrator

    config = _load_config(config_path)
    try:
        config = _filter_tickers(config, category, ticker)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    base_dir = Path(config_path).resolve().parent
    output_path = _resolve(config, base_dir, "json_path", "output/output.json")

    # When merging, snapshot the existing output BEFORE running the pipeline.
    old_output: dict[str, Any] | None = None
    if merge and output_path.exists():
        with output_path.open("r", encoding="utf-8") as fh:
            old_output = json.load(fh)
        print(f"[merge] Loaded existing output: {output_path}")

    label = category or ticker or "all"
    print(f"[1/2] Orchestration with {config_path} (tickers: {label}) ...")
    output = run_orchestrator(config_path, config=config)

    if merge and old_output is not None:
        print("[merge] Merging new results with existing data ...")
        output = _merge_output(old_output, output, config_path)
        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(output, fh, indent=2)
        print(f"[merge] Output written: {output_path}")

    summary = output.get("stale_summary", {})
    print(
        f"      sources: {summary.get('fresh', 0)}/{summary.get('total_sources', 0)} "
        f"fresh · reliability: {summary.get('signal_reliability', '?')}"
    )
    _render_report(config_path)
    return 0


def mode_report_only(config_path: str) -> int:
    """Render the HTML report from the existing output.json (no scraping)."""
    _render_report(config_path)
    return 0


def mode_override_only(config_path: str) -> int:
    """Apply valid manual overrides to the existing output.json and re-render.

    No scraping: loads output.json, applies manual overrides with the same
    priority as the orchestrator (scraping > manual > missing), rebuilds the
    indicator matrix from the updated results and renders the HTML report.
    """
    base_dir = Path(config_path).resolve().parent
    config = _load_config(config_path)
    output_path = _resolve(config, base_dir, "json_path", "output/output.json")
    db_path = _resolve(config, base_dir, "db_path", "output/scraper_audit.db")

    if not output_path.exists():
        print(f"Output JSON not found: {output_path}. Run 'run.py' first.", file=sys.stderr)
        return 1

    with output_path.open("r", encoding="utf-8") as fh:
        existing = json.load(fh)

    # Rebuild results from the persisted output (drop meta keys).
    results: dict[str, Any] = {}
    for key, value in existing.items():
        if isinstance(value, dict) and "status" in value:
            results[key] = value

    # Apply manual overrides (same priority as orchestrator).
    from manual_overrides import apply_overrides, load_validated_overrides

    strategy_cfg = config.get("strategy", {})
    overrides_path = base_dir / strategy_cfg.get("manual_overrides", "manual_overrides.yaml")
    force_keys = strategy_cfg.get("force_manual_overrides", []) or []
    overrides, errors = load_validated_overrides(str(overrides_path))
    for error in errors:
        print(f"  [warn] {error}")
    print("[1/2] Applying manual overrides ...")
    results = apply_overrides(results, overrides, force_keys=force_keys)
    for key in overrides:
        status = results.get(key, {}).get("status", "?")
        origin = results.get(key, {}).get("origin", "?")
        print(f"      {key}: status={status} origin={origin}")

    # Rebuild the consolidated output (stale_summary) and indicator matrix.
    from consolidator import consolidate
    from orchestrator import _build_strategy_indicators

    print("[2/2] Rebuilding output + report ...")
    output = consolidate(results)
    output["strategy_indicators"] = _build_strategy_indicators(config, base_dir, results)

    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"      output: {output_path}")

    _render_report(config_path)
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(
        description="Run scraper-system (full, report-only, or override-only)"
    )
    parser.add_argument(
        "config",
        nargs="?",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml relative to project root)",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only render the HTML report from the existing output.json",
    )
    parser.add_argument(
        "--override-only",
        action="store_true",
        help="Apply manual overrides to the existing output.json and re-render (no scraping)",
    )
    parser.add_argument(
        "--category",
        help="Scrape only the specified category (e.g. semiconductors)",
    )
    parser.add_argument(
        "--ticker",
        help="Scrape only the specified ticker symbol (e.g. NVDA)",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge new scrape results into existing output.json (preserves other tickers/categories)",
    )
    args = parser.parse_args()

    config_path = str(PROJECT_ROOT / args.config)
    if not Path(config_path).exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1

    if args.report_only:
        return mode_report_only(config_path)
    if args.override_only:
        return mode_override_only(config_path)
    return mode_full(
        config_path,
        category=args.category,
        ticker=args.ticker,
        merge=args.merge,
    )


if __name__ == "__main__":
    raise SystemExit(main())
