"""FGI (Fear & Greed Index) scraper module with multi-source fallback.

Fetches the Fear & Greed Index score (0-100) and zone label by trying a chain
of three sources in order — CNN API, feargreedmeter.com, feargreedindex.net —
via ``fetch_utils.fetch_first_success``. Each source has its own body parser
(``parse_cnn``, ``parse_feargreedmeter``, ``parse_feargreedindex``) and the
winning source name is recorded in the result as ``source``.

Entry point: ``run(config) -> dict`` (config-driven, per technical-domain.md).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from fetch_utils import fetch_first_success, try_parsers

# Source chain, in fallback order (primary first).
FGI_API_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
FGI_METER_URL = "https://feargreedmeter.com/"
FGI_INDEX_URL = "https://feargreedindex.net/api/fear-greed"

DEFAULT_SOURCES: list[dict[str, str]] = [
    {"name": "cnn", "url": FGI_API_URL},
    {"name": "feargreedmeter", "url": FGI_METER_URL},
    {"name": "feargreedindex", "url": FGI_INDEX_URL},
]

# Zone bands over the 0-100 scale, aligned to the strategy's Regola 0
# (specifiche_strategia.md F1): Extreme Fear 0-24, Fear 25-44, Neutral 45-55,
# Greed 56-74, Extreme Greed 75-100.
ZONE_BANDS: tuple[tuple[float, float, str], ...] = (
    (0.0, 25.0, "extreme fear"),
    (25.0, 45.0, "fear"),
    (45.0, 56.0, "neutral"),
    (56.0, 75.0, "greed"),
    (75.0, 101.0, "extreme greed"),
)

DEFAULT_TIMEOUT = 15
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 2.0
DEFAULT_STALE_AFTER_HOURS = 24
FREQUENCY = "daily"
# Browser-like headers required: CNN blocks generic/script User-Agents (HTTP 418).
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.cnn.com/",
    "Origin": "https://www.cnn.com",
}


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def zone_from_score(score: float) -> str:
    """Map a 0-100 score to its zone label."""
    for low, high, label in ZONE_BANDS:
        if low <= score < high:
            return label
    return "extreme"


def parse_score(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract score and zone from the CNN API JSON payload (dict form)."""
    fng = payload["fear_and_greed"]
    score = float(fng["score"])
    zone = str(fng.get("rating") or "").strip().lower() or zone_from_score(score)
    return {"score": score, "zone": zone}


# Chiavi API CNN → chiavi progetto (snake_case). Ordinate come nel payload CNN.
COMPONENT_KEYS: tuple[tuple[str, str], ...] = (
    ("market_momentum_sp500", "market_momentum"),
    ("stock_price_strength", "stock_price_strength"),
    ("stock_price_breadth", "stock_price_breadth"),
    ("put_call_options", "put_call_options"),
    ("market_volatility_vix", "market_volatility"),
    ("junk_bond_demand", "junk_bond_demand"),
    ("safe_haven_demand", "safe_haven_demand"),
)


def parse_components(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract the 7 FGI sub-indicators from the CNN API payload.

    Each component is mapped to a snake_case project key and carries
    ``score`` (0-100) and ``rating`` (label). Fail-soft per component: a
    missing or malformed key is skipped, the others remain.

    Returns:
        dict mapping project key → {"score": float, "rating": str}. Empty
        dict when no component is valid.
    """
    result: dict[str, dict[str, Any]] = {}
    for api_key, project_key in COMPONENT_KEYS:
        raw = payload.get(api_key)
        if not isinstance(raw, dict):
            continue
        try:
            score = float(raw["score"])
            rating = str(raw["rating"]).strip().lower()
        except (KeyError, TypeError, ValueError):
            continue
        if not rating:
            continue
        result[project_key] = {"score": score, "rating": rating}
    return result


def parse_cnn(payload: str) -> dict[str, Any]:
    """Parse the CNN API JSON payload (primary source)."""
    return parse_score(json.loads(payload))


def parse_feargreedmeter(html: str) -> dict[str, Any]:
    """Parse the feargreedmeter.com title: 'Fear and Greed Index: N (Label)'.

    The site publishes BOTH a stock-market index and a crypto index; the title
    explicitly names the stock variant ("... | Stock Market Sentiment"). To
    prevent semantic drift (a title change could surface the crypto value), the
    parser requires the stock-market marker in the same document.

    Raises:
        ValueError: If the title or the stock-market marker is missing.
    """
    match = re.search(r"Fear and Greed Index:\s*([\d.]+)\s*\(([^)]+)\)", html)
    if not match:
        raise ValueError("feargreedmeter value not found in HTML")
    if "stock market" not in html.lower():
        raise ValueError("feargreedmeter page does not identify the stock market index")
    score = float(match.group(1))
    zone = match.group(2).strip().lower()
    return {"score": score, "zone": zone}


def parse_feargreedindex(body: str) -> dict[str, Any]:
    """Parse the feargreedindex.net API JSON payload.

    The API exposes both ``value`` and ``baseValue``. ``value`` includes the
    community votes the site collects (see ``votes`` field), while ``baseValue``
    is the objective index value before those votes — which is what we want for
    a strategy signal. ``baseValue`` is used when present, falling back to
    ``value`` for older payloads.

    Raises:
        ValueError: If the payload cannot be parsed.
    """
    data = json.loads(body)
    score = float(data.get("baseValue", data["value"]))
    zone = str(data.get("label", "")).strip().lower()
    return {"score": score, "zone": zone}


def parse_html(html: str) -> dict[str, Any]:
    """Best-effort parse of the FGI gauge value from raw HTML (legacy fallback)."""
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one("span.market-fng-gauge__dial-number-value")
    if node is None:
        raise ValueError("FGI gauge value not found in HTML")
    score = float(node.get_text(strip=True))
    return {"score": score, "zone": zone_from_score(score)}


def build_result(score: float, zone: str, fetched_at: str) -> dict[str, Any]:
    """Build the output dict in the file.json format."""
    return {
        "score": score,
        "zone": zone,
        "fetched_at": fetched_at,
        "frequency": FREQUENCY,
        "stale_after_hours": DEFAULT_STALE_AFTER_HOURS,
        "status": "fresh",
    }


def run(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch and return the FGI result as a structured dict.

    Args:
        config: Optional overrides (sources, timeout, retries, backoff, headers).
    """
    config = config or {}
    sources = config.get("sources") or DEFAULT_SOURCES
    source_list = [(s["name"], s["url"]) for s in sources]
    timeout = config.get("timeout", DEFAULT_TIMEOUT)
    retries = config.get("retries", DEFAULT_RETRIES)
    backoff = config.get("backoff", DEFAULT_BACKOFF)
    headers = config.get("headers", DEFAULT_HEADERS)

    parsers = {
        "cnn": parse_cnn,
        "feargreedmeter": parse_feargreedmeter,
        "feargreedindex": parse_feargreedindex,
    }

    def _accepts(source_name: str, body: str) -> bool:
        """Reject a source whose body its own parser cannot handle (content
        aware fallback: 200 with a block/consent page counts as failure)."""
        try:
            parsers[source_name](body)
            return True
        except (ValueError, KeyError, TypeError):
            return False

    with requests.Session() as session:
        session.headers.update(headers)
        body, source = fetch_first_success(
            session, source_list, timeout, retries, backoff, validate=_accepts
        )

    parser_list = [(source, parsers[source])]
    data, _ = try_parsers(body, parser_list)
    result = build_result(data["score"], data["zone"], _now_iso())
    result["source"] = source
    return result
