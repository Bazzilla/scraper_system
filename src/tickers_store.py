"""Read/write access to the ``tickers`` section of config.yaml.

Pure functions used by the local tickers editor (see ``tickers_page.py`` and
the ``/tickers.html`` routes in ``overrides_server.py``):

- ``load_tickers(config_path)``   → current tickers mapping (raw metadata kept)
- ``backup_config(config_path)``  → copy of the YAML named with an epoch
  timestamp (number encoding date+time), stored under ``backups/``
- ``save_tickers(config_path, tickers)`` → validate + backup + rewrite ONLY
  the ``tickers`` section, splicing the new block into the file text so every
  comment elsewhere in config.yaml is preserved (ruamel.yaml is not a
  dependency).
"""

from __future__ import annotations

import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from config_loader import normalize_tickers

_TICKERS_HEADING = re.compile(r"^tickers:.*$", re.M)

_HEADER_COMMENT = """\
  # Classificazione strategica (display-only nel report, MAI segnale BUY):
  # - quality_tier: core | secondary | opportunistic
  # - strategy_role: ruolo strategico (compounder, defense_prime, ...)
  # - buy_the_dip_validity: high | medium | low (coerenza con la strategia BTD)
  # - notes: motivazione leggibile nel report (opzionale)
"""


def load_tickers(config_path: str) -> dict[str, Any]:
    """Return the raw ``tickers`` section of config.yaml ({} if absent)."""
    with open(config_path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}
    tickers = config.get("tickers", {})
    if not isinstance(tickers, dict):
        raise ValueError("Config 'tickers' must be a mapping")
    return tickers


def backup_config(config_path: str, now: datetime | None = None) -> Path:
    """Copy config.yaml to ``backups/config-<epoch>.yaml`` (epoch = date+time).

    Returns the backup path. The numeric name makes backups trivially
    sortable and collision-free within a second.
    """
    now = now or datetime.now(timezone.utc)
    source = Path(config_path)
    backup_dir = source.resolve().parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(now.timestamp())
    backup_path = backup_dir / f"config-{stamp}.yaml"
    shutil.copy2(source, backup_path)
    return backup_path


def _scalar(value: Any) -> str:
    """Render a scalar with proper YAML quoting (safe_dump of the bare value).

    NB: solo la prima riga — safe_dump di uno scalare nudo aggiunge il
    marcatore di fine documento ``...`` su una riga separata.
    """
    return yaml.safe_dump(value, allow_unicode=True, width=4096).splitlines()[0]


def _uppercase_symbols(tickers: dict[str, Any]) -> dict[str, Any]:
    """Normalize ticker symbols to UPPERCASE (convention + duplicate check)."""
    normalized: dict[str, Any] = {}
    for category, entries in tickers.items():
        new_entries = []
        for entry in entries:
            entry = dict(entry)
            if isinstance(entry.get("symbol"), str):
                entry["symbol"] = entry["symbol"].strip().upper()
            new_entries.append(entry)
        normalized[category] = new_entries
    return normalized


def dump_tickers_block(tickers: dict[str, Any]) -> str:
    """Render the ``tickers`` section as YAML text (pretty, stable order)."""
    lines: list[str] = ["tickers:", _HEADER_COMMENT.rstrip("\n")]
    for category, entries in tickers.items():
        lines.append(f"  {_scalar(str(category))}:")
        for entry in entries:
            for i, (key, value) in enumerate(entry.items()):
                prefix = "    - " if i == 0 else "      "
                lines.append(f"{prefix}{_scalar(str(key))}: {_scalar(value)}")
    return "\n".join(lines) + "\n"


def _splice_tickers(original: str, block: str) -> str:
    """Replace the text from the ``tickers:`` heading to EOF with ``block``.

    Everything before the heading (comments included) is preserved verbatim.
    If no ``tickers:`` heading exists, the block is appended after a blank
    line.
    """
    match = _TICKERS_HEADING.search(original)
    if match is None:
        return original.rstrip("\n") + "\n\n" + block
    return original[: match.start()] + block


def save_tickers(
    config_path: str,
    tickers: dict[str, Any],
    now: datetime | None = None,
) -> Path:
    """Validate, backup and persist the ``tickers`` section of config.yaml.

    Validation reuses ``normalize_tickers`` (duplicate symbols, non-empty
    categories, metadata whitelist) so the pipeline never sees an invalid
    config. On validation error NOTHING is written and NO backup is created.

    Returns:
        The path of the backup created before the write.
    """
    normalized = normalize_tickers(_uppercase_symbols(tickers))  # raises ValueError
    path = Path(config_path)
    original = path.read_text(encoding="utf-8")
    backup_path = backup_config(str(path), now=now)
    path.write_text(_splice_tickers(original, dump_tickers_block(normalized)), encoding="utf-8")
    return backup_path


def _now_epoch() -> int:
    return int(time.time())
