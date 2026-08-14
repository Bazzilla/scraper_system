"""Consolidate scraper results into the file.json output format.

Pure function: takes a dict of per-scraper results and returns the
consolidated output dict (generated_at + per-source keys + stale_summary).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _build_stale_summary(results: dict[str, Any]) -> dict[str, Any]:
    """Summarize fresh/stale/error status across sources.

    Fail-closed: a source with status "error" counts as stale and drops the
    reliability to "low" (the data is not trustworthy when a signal is
    missing). With zero sources the reliability is "low" — an all-down system
    must never be reported as "high".
    """
    total = 0
    fresh = 0
    stale = 0
    errors = 0
    stale_details: list[str] = []

    for key, value in results.items():
        if isinstance(value, dict) and "status" in value:
            total += 1
            status = value["status"]
            if status == "fresh":
                fresh += 1
            elif status == "error":
                errors += 1
                stale += 1
                error_msg = str(value.get("error") or "unknown")
                stale_details.append(f"{key}: error ({error_msg[:80]})")
            else:
                stale += 1
                stale_details.append(f"{key}: {status}")

    if total == 0:
        reliability = "low"
    elif errors > 0:
        reliability = "low"
    elif stale > 0:
        reliability = "medium"
    else:
        reliability = "high"

    return {
        "total_sources": total,
        "fresh": fresh,
        "stale": stale,
        "errors": errors,
        "stale_details": stale_details,
        "signal_reliability": reliability,
    }


def consolidate(
    results: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Merge per-scraper results into a single output dict."""
    output: dict[str, Any] = {"generated_at": generated_at or _now_iso()}
    output.update(results)
    output["stale_summary"] = _build_stale_summary(results)
    return output