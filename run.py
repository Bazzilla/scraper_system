"""Run the full pipeline in one shot: orchestration + HTML report.

Usage (from the project root):

    ./.venv/bin/python run.py [config.yaml]

Equivalent to running:
    1. orchestrator.run(config)   → output/output.json + output/scraper_audit.db
    2. report_html.render(config) → output/report.html

The script works from any directory: it resolves paths relative to the
project root (the directory containing this file). The config path is
optional and defaults to ``config.yaml``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make src/ importable regardless of the current working directory.
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run scraper-system: orchestration + HTML report"
    )
    parser.add_argument(
        "config",
        nargs="?",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml relative to project root)",
    )
    args = parser.parse_args()

    config_path = str(PROJECT_ROOT / args.config)
    if not Path(config_path).exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1

    # 1. Orchestration (scrapers → output.json + audit db)
    from orchestrator import run as run_orchestrator

    print(f"[1/2] Orchestration with {config_path} ...")
    output = run_orchestrator(config_path)
    summary = output.get("stale_summary", {})
    print(
        f"      sources: {summary.get('fresh', 0)}/{summary.get('total_sources', 0)} "
        f"fresh · reliability: {summary.get('signal_reliability', '?')}"
    )

    # 2. HTML report (output.json → report.html)
    from report_html import render as render_report

    print("[2/2] Rendering HTML report ...")
    report_path = render_report(config_path)
    print(f"      report: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
