"""Manual overrides — user-entered values for fragile indicators.

Reads ``manual_overrides.yaml`` (validated before use) and applies it to the
orchestrator's results with a strict, fail-closed priority:

    scraping (fresh) > manual override (valid + fresh) > missing/error

Rules (audit 2026-08-14):
- An override is NEVER confused with a scraped value: manual results carry
  ``source: "manual"`` and ``origin: "manual"``.
- An override must be schema-valid; malformed entries are logged and ignored
  (they never break the pipeline).
- An override expires after ``stale_after_hours`` from ``fetched_at``: expired
  overrides result in ``status: "stale"`` and are never used in scoring.
- If both scraping and a valid override exist, scraping wins by default.
  ``force_manual_overrides`` in config.yaml can override that — but it is
  DISABLED by default (fail-closed).

Supported indicators (fields they must provide):
    aaii  -> bullish, neutral, bearish
    fgi   -> score (+ optional zone)
    naaim -> exposure
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_OVERRIDES_PATH = "manual_overrides.yaml"

# Frequency per indicator (used for the output "frequency" field).
_FREQUENCY: dict[str, str] = {
    "aaii": "weekly",
    "fgi": "daily",
    "naaim": "weekly",
}

# Required value fields per supported indicator key.
_REQUIRED_FIELDS: dict[str, list[str]] = {
    "aaii": ["bullish", "neutral", "bearish"],
    "fgi": ["score"],
    "naaim": ["exposure"],
}

# Common required metadata for every override.
_COMMON_REQUIRED = ("fetched_at", "stale_after_hours", "entered_by")


class OverrideValidationError(ValueError):
    """Raised when an override entry is malformed (caught and logged)."""


def load_overrides(path: str | None = None) -> dict[str, Any]:
    """Load the raw manual overrides YAML.

    Args:
        path: Path to the overrides file. Defaults to ``manual_overrides.yaml``
            resolved against the project root when the current directory is
            ``src/``.

    Returns:
        The raw mapping (``{"aaii": {...}, ...}``). A missing or empty file
        yields an empty dict (never raises).

    Raises:
        ValueError: If the file exists but is not a mapping.
    """
    overrides_path = _resolve_path(path)
    if not overrides_path.exists():
        logger.info("Manual overrides file not found: %s — ignoring", overrides_path)
        return {}
    with overrides_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError("manual_overrides.yaml must be a mapping")
    return data


def validate_entry(key: str, entry: Any) -> dict[str, Any]:
    """Validate one override entry, returning a cleaned copy.

    Raises:
        OverrideValidationError: If the entry is malformed (missing fields,
            wrong types, unparsable timestamp, non-positive stale window).
    """
    if not isinstance(entry, dict):
        raise OverrideValidationError(f"{key}: override must be a mapping")

    for field in _COMMON_REQUIRED:
        if field not in entry:
            raise OverrideValidationError(f"{key}: missing required field {field!r}")

    fetched_at = _parse_iso(entry["fetched_at"])
    stale_after_hours = entry["stale_after_hours"]
    if not isinstance(stale_after_hours, (int, float)) or stale_after_hours <= 0:
        raise OverrideValidationError(
            f"{key}: stale_after_hours must be a positive number"
        )

    entered_by = entry["entered_by"]
    if not isinstance(entered_by, str) or not entered_by.strip():
        raise OverrideValidationError(f"{key}: entered_by must be a non-empty string")

    required = _REQUIRED_FIELDS.get(key)
    if required is None:
        raise OverrideValidationError(f"{key}: indicator not supported for override")

    values: dict[str, Any] = {}
    for field in required:
        value = entry.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise OverrideValidationError(
                f"{key}: field {field!r} must be a number"
            )
        values[field] = float(value)

    note = entry.get("note")
    if note is not None and not isinstance(note, str):
        raise OverrideValidationError(f"{key}: note must be a string")

    zone = entry.get("zone")
    if zone is not None and not isinstance(zone, str):
        raise OverrideValidationError(f"{key}: zone must be a string")

    return {
        **values,
        "source": "manual",
        "origin": "manual",
        "fetched_at": fetched_at.isoformat(),
        "stale_after_hours": int(stale_after_hours),
        "entered_by": entered_by.strip(),
        "note": note.strip() if note else None,
        **({"zone": zone.strip()} if zone else {}),
    }


def load_validated_overrides(
    path: str | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Load and validate all overrides.

    Returns:
        (valid_overrides, errors): valid entries keyed by indicator name, and a
        list of human-readable error messages for the malformed ones. Errors
        are logged and do NOT break the pipeline.
    """
    raw = load_overrides(path)
    valid: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for key, entry in raw.items():
        try:
            valid[key] = validate_entry(key, entry)
        except OverrideValidationError as error:
            logger.warning("Manual override ignored: %s", error)
            errors.append(str(error))
    return valid, errors


def is_fresh(override: dict[str, Any], now: datetime | None = None) -> bool:
    """Whether an override is still within its validity window."""
    now = now or datetime.now(timezone.utc)
    fetched = datetime.fromisoformat(override["fetched_at"])
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return (now - fetched).total_seconds() <= override["stale_after_hours"] * 3600


def build_manual_result(
    key: str,
    override: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the output dict for a valid, fresh manual override.

    The result is explicitly marked ``source: "manual"`` and
    ``origin: "manual"`` so it can never be confused with a scraped value.
    """
    now = now or datetime.now(timezone.utc)
    result: dict[str, Any] = {
        "source": "manual",
        "origin": "manual",
        "fetched_at": override["fetched_at"],
        "frequency": _FREQUENCY.get(key, "daily"),
        "stale_after_hours": override["stale_after_hours"],
        "entered_by": override["entered_by"],
        "status": "fresh",
    }
    if key == "aaii":
        result["bullish"] = override["bullish"]
        result["neutral"] = override["neutral"]
        result["bearish"] = override["bearish"]
    elif key == "fgi":
        result["score"] = override["score"]
        result["zone"] = override.get("zone") or "unknown"
    elif key == "naaim":
        result["exposure"] = override["exposure"]
    if override.get("note"):
        result["note"] = override["note"]
    result["checked_at"] = now.isoformat()
    return result


def build_stale_manual_result(
    key: str,
    override: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the output dict for an EXPIRED override.

    The data is kept visible for traceability but marked stale: it is never
    usable in scoring.
    """
    result = build_manual_result(key, override, now)
    result["status"] = "stale"
    result["note"] = "Override manuale scaduto"
    return result


def apply_overrides(
    results: dict[str, Any],
    overrides: dict[str, dict[str, Any]],
    force_keys: set[str] | list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply valid manual overrides to scraper results.

    Priority (fail-closed): scraping (fresh) > manual override (valid + fresh)
    > missing/error. Scraping wins by default; ``force_keys`` (from
    ``strategy.force_manual_overrides``) makes the override win even when the
    scraper succeeded.

    Returns a new results dict (the input is not mutated).
    """
    force = set(force_keys or ())
    now = now or datetime.now(timezone.utc)
    merged = dict(results)

    for key, override in overrides.items():
        scraped = results.get(key)
        # "Scraping wins" vale SOLO per dati realmente scrapati (origin=scraped).
        # Un risultato manuale persistito (origin=manual, es. da un run
        # --override-only precedente) NON deve bloccare un override più recente.
        scraped_ok = (
            isinstance(scraped, dict)
            and scraped.get("status") == "fresh"
            and scraped.get("origin") == "scraped"
        )
        if scraped_ok and key not in force:
            continue  # scraping wins (default)

        if is_fresh(override, now):
            merged[key] = build_manual_result(key, override, now)
        else:
            # Override scaduto: fail-closed — non usare nello score, ma tieni
            # traccia. Se c'era un risultato fresh (caso force), resta fresh
            # scraped; altrimenti il dato manuale scaduto diventa stale.
            if key not in results or results[key].get("status") != "fresh":
                merged[key] = build_stale_manual_result(key, override, now)
    return merged


def _parse_iso(value: Any) -> datetime:
    if not isinstance(value, str):
        raise OverrideValidationError("fetched_at must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OverrideValidationError(
            f"fetched_at not a valid ISO 8601 timestamp: {value!r}"
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _resolve_path(path: str | None) -> Path:
    if path:
        return Path(path)
    candidate = Path(DEFAULT_OVERRIDES_PATH)
    if candidate.exists():
        return candidate
    return _PROJECT_ROOT / DEFAULT_OVERRIDES_PATH


# Fallback per lookup da src/: il file vive nella radice del progetto.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
