"""Generic fallback helpers for scraper modules.

``fetch_first_success`` tries a list of sources in order and returns the first
that responds. ``try_parsers`` tries a list of parsers on the same body and
returns the first that succeeds. Both are used by modules whose primary source
is unstable (e.g. FGI), following the project's resilience pattern.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)


def fetch_first_success(
    session: requests.Session,
    sources: list[tuple[str, str]],
    timeout: int,
    retries: int,
    backoff: float,
    validate: Callable[[str, str], bool] | None = None,
) -> tuple[str, str]:
    """Fetch the first source (name, url) that responds.

    When ``validate`` is provided, a source also counts as failed when the
    validator rejects its body — this makes the fallback content-aware (a
    source returning 200 with an unparseable block/consent page is skipped).

    Returns:
        (body, source_name) of the first successful source.
    Raises:
        RuntimeError: If every source fails after its retries.
    """
    failures: list[str] = []
    for name, url in sources:
        try:
            body = _fetch_with_retry(session, url, timeout, retries, backoff)
            if validate is not None and not validate(name, body):
                raise ValueError(f"body rejected by validator for {name}")
            return body, name
        except (requests.RequestException, ValueError) as error:
            failures.append(f"{name}: {error}")
            logger.warning("Source %s failed: %s", name, error)
    raise RuntimeError(
        f"All sources failed: {'; '.join(failures)}"
    )


def try_parsers(
    body: str,
    parsers: list[tuple[str, Callable[[str], Any]]],
) -> tuple[Any, str]:
    """Run the first parser (name, func) that succeeds on ``body``.

    Returns:
        (result, parser_name) of the first successful parser.
    Raises:
        ValueError: If every parser fails.
    """
    failures: list[str] = []
    for name, parser in parsers:
        try:
            return parser(body), name
        except (ValueError, KeyError, TypeError) as error:
            failures.append(f"{name}: {error}")
            logger.warning("Parser %s failed: %s", name, error)
    raise ValueError(f"All parsers failed: {'; '.join(failures)}")


def _fetch_with_retry(
    session: requests.Session,
    url: str,
    timeout: int,
    retries: int,
    backoff: float,
) -> str:
    """Fetch a URL with retry and exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.text
        except (requests.RequestException, ValueError) as error:
            last_error = error
            logger.warning(
                "Fetch attempt %d/%d failed: %s", attempt + 1, retries, error
            )
            if attempt < retries - 1:
                time.sleep(backoff * (2**attempt))
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Fetch failed after {retries} attempts")
