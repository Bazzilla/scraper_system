"""Indicator registry — strategy coverage matrix.

Loads ``indicator_registry.yaml`` (the machine-readable matrix describing each
strategy indicator) and combines it with runtime data to produce DISTINCT
semantic fields per indicator:

- ``coverage`` (STATIC, from strategy specs):
    true = the indicator BELONGS to the strategy (it is listed in
    specifiche_strategia.md / the R/O matrix). Never depends on runtime:
    stays true even if not implemented, not scrapable, broken, fed only
    manually, or not usable in scoring. false = informational artifact
    the project added that is NOT part of the strategy (e.g. VIX spot).

- ``implementation_status`` (STATIC):
    implemented      = a module produces the data with strategy-equivalent
                       semantics.
    proxy            = the project produces DIFFERENT data (non-equivalent
                       semantics) to approximate the indicator, or a
                       non-strategic informational artifact.
    missing          = no implementation (declared gap).
    manual_supported = no scraper, but the project supports manual entry via
                       manual_overrides.yaml.

- ``availability`` (DYNAMIC, runtime): the data is really available today
    (module produced "fresh", or a fresh manual override exists).

- ``usable_in_strategy_score`` (DERIVED): true only when coverage=true AND
    availability=true AND implementation_status in (implemented,
    manual_supported) OR (proxy AND key in strategy.proxy_accepted).
    Fail-closed: missing never; coverage=false never; unavailable never.

- ``source`` (DYNAMIC, runtime): scraped | manual | missing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_REGISTRY_PATH = "indicator_registry.yaml"

# Implementation statuses (static).
STATUS_IMPLEMENTED = "implemented"
STATUS_PROXY = "proxy"
STATUS_MISSING = "missing"
STATUS_MANUAL_SUPPORTED = "manual_supported"

# Runtime availability states produced by the orchestrator.
_STATUS_FRESH = "fresh"


def load_registry(path: str | None = None) -> dict[str, Any]:
    """Load the indicator registry YAML.

    Args:
        path: Path to the registry file. Defaults to ``indicator_registry.yaml``
            resolved against the project root when the current directory is
            ``src/``.

    Returns:
        The raw registry mapping (``{"indicators": {...}}``).

    Raises:
        FileNotFoundError: If the registry file does not exist.
    """
    registry_path = _resolve_registry_path(path)
    with registry_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    indicators = data.get("indicators")
    if not isinstance(indicators, dict):
        raise ValueError("indicator_registry.yaml must contain an 'indicators' mapping")
    return {"indicators": indicators}


def normalize_registry(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize registry entries: fill defaults and validate fields.

    Returns a copy with every entry guaranteed to have ``coverage``,
    ``implementation_status``, ``semantic_coherent`` and ``output_key``.

    Raises:
        ValueError: If an entry has an invalid implementation_status.
    """
    normalized: dict[str, Any] = {}
    for key, entry in raw.get("indicators", {}).items():
        if not isinstance(entry, dict):
            raise ValueError(f"Registry entry {key!r} must be a mapping")
        impl = entry.get("implementation_status", entry.get("status", STATUS_MISSING))
        if impl not in (
            STATUS_IMPLEMENTED,
            STATUS_PROXY,
            STATUS_MISSING,
            STATUS_MANUAL_SUPPORTED,
        ):
            raise ValueError(
                f"Registry entry {key!r} has invalid implementation_status {impl!r}"
            )
        normalized[key] = {
            "name": entry.get("name", key),
            "strategy_ref": entry.get("strategy_ref", ""),
            "coverage": bool(entry.get("coverage", False)),
            "implementation_status": impl,
            "primary_source": entry.get("primary_source"),
            "fallbacks": list(entry.get("fallbacks", [])),
            "semantic_coherent": bool(entry.get("semantic_coherent", False)),
            "output_key": entry.get("output_key"),
            "notes": entry.get("notes", ""),
        }
    return {"indicators": normalized}


def build_availability(
    registry: dict[str, Any],
    runtime_status: dict[str, str],
) -> dict[str, bool]:
    """Map runtime module status to per-indicator availability.

    For each indicator, if it has an ``output_key`` and that key's runtime
    status is "fresh", the indicator is available. Indicators without an
    output_key (missing/never-implemented) are unavailable.
    """
    availability: dict[str, bool] = {}
    for key, entry in registry.get("indicators", {}).items():
        output_key = entry.get("output_key")
        if output_key is None:
            availability[key] = False
        else:
            availability[key] = (
                runtime_status.get(output_key) == _STATUS_FRESH
            )
    return availability


def coverage_for(entry: dict[str, Any]) -> bool:
    """Coverage: the indicator belongs to the strategy (from the specs).

    This is a STATIC property declared in the registry YAML — it never depends
    on runtime state. A strategy indicator keeps coverage=true even when not
    implemented, broken, manual-only, or unusable in scoring.
    """
    return bool(entry.get("coverage", False))


def usable_for(
    key: str,
    entry: dict[str, Any],
    availability: dict[str, bool],
    proxy_accepted: set[str] | list[str] | None = None,
) -> bool:
    """Usable-in-score: strategy indicator AND available AND implementable.

    Rules (fail-closed):
    - coverage=false  → False (non-strategic artifacts never enter scoring)
    - missing         → False (never)
    - not available   → False (runtime)
    - implemented     → True (if available)
    - manual_supported → True (if available — a valid manual value IS the
      strategy indicator; e.g. NAAIM fed via manual_overrides.yaml)
    - proxy           → True only if key in proxy_accepted AND available
    """
    accepted = set(proxy_accepted or ())
    is_available = availability.get(key, False)
    if not coverage_for(entry):
        return False
    if not is_available:
        return False
    impl = entry.get("implementation_status")
    if impl == STATUS_IMPLEMENTED:
        return True
    if impl == STATUS_MANUAL_SUPPORTED:
        return True
    if impl == STATUS_PROXY:
        return key in accepted
    return False


def summarize(
    registry: dict[str, Any],
    proxy_accepted: set[str] | list[str] | None = None,
    availability: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Compute the per-indicator strategy coverage summary.

    Args:
        registry: Normalized registry (see ``normalize_registry``).
        proxy_accepted: Keys of proxy indicators explicitly accepted in config.
        availability: Per-indicator runtime availability (from
            ``build_availability``). If None, every indicator is treated as
            available (used by unit tests; the orchestrator always passes it).

    Returns:
        A machine-readable dict with, per indicator key: name, strategy_ref,
        coverage, implementation_status, primary_source, fallbacks,
        semantic_coherent, availability, usable_in_strategy_score, notes —
        plus a ``summary`` section grouping keys by implementation_status,
        by coverage, by availability and by usability.
    """
    accepted = set(proxy_accepted or ())
    result: dict[str, Any] = {}
    by_impl: dict[str, list[str]] = {
        STATUS_IMPLEMENTED: [],
        STATUS_PROXY: [],
        STATUS_MISSING: [],
        STATUS_MANUAL_SUPPORTED: [],
    }
    covered: list[str] = []
    available: list[str] = []
    usable_in_score: list[str] = []

    for key, entry in registry.get("indicators", {}).items():
        coverage = coverage_for(entry)
        avail = availability.get(key, True) if availability is not None else True
        usable = usable_for(key, entry, {key: avail}, accepted)

        entry["coverage"] = coverage
        entry["availability"] = avail
        entry["usable_in_strategy_score"] = usable
        result[key] = dict(entry)

        by_impl.setdefault(entry["implementation_status"], []).append(key)
        if coverage:
            covered.append(key)
        if avail:
            available.append(key)
        if usable:
            usable_in_score.append(key)

    result["_meta"] = {
        "proxy_accepted": sorted(accepted),
        "note": (
            "coverage (statico, da specifiche strategiche): appartiene alla "
            "strategia; implementation_status (statico): implemented/proxy/"
            "missing/manual_supported; availability (runtime): dato disponibile "
            "oggi; usable_in_strategy_score (derivato): coverage E disponibile "
            "E implementabile (o proxy accettato). Fail-closed."
        ),
    }
    result["summary"] = {
        "implemented": by_impl.get(STATUS_IMPLEMENTED, []),
        "proxy": by_impl.get(STATUS_PROXY, []),
        "missing": by_impl.get(STATUS_MISSING, []),
        "manual_supported": by_impl.get(STATUS_MANUAL_SUPPORTED, []),
        "covered": sorted(covered),
        "not_covered": sorted(set(registry.get("indicators", {})) - set(covered)),
        "available": sorted(available),
        "unavailable": sorted(set(registry.get("indicators", {})) - set(available)),
        "usable_in_score": sorted(usable_in_score),
    }
    return result


def load_and_summarize(
    registry_path: str | None = None,
    proxy_accepted: set[str] | list[str] | None = None,
    availability: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Load, normalize and summarize the registry in one call."""
    raw = load_registry(registry_path)
    normalized = normalize_registry(raw)
    return summarize(normalized, proxy_accepted, availability)


def _resolve_registry_path(path: str | None) -> Path:
    if path:
        return Path(path)
    candidate = Path(DEFAULT_REGISTRY_PATH)
    if candidate.exists():
        return candidate
    return _PROJECT_ROOT / DEFAULT_REGISTRY_PATH


# Fallback per lookup da src/: il registry vive nella radice del progetto.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
