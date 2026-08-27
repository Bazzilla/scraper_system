"""Local mini-server for editing manual overrides, ticker lists and re-rendering.

Serves:
    GET  /                → redirect to the dashboard (/report.html)
    GET  /overrides.html  → the overrides entry page (overrides_page.render_overrides_page)
    GET  /api/data        → JSON of the current manual_overrides.yaml
    POST /api/save        → validate + save one override, then rebuild output + report
    GET  /report.html     → the existing output/report.html
    GET  /tickers.html    → ticker lists editor page (tickers_page.render_tickers_page)
    GET  /api/tickers     → JSON of the current tickers section of config.yaml
    POST /api/tickers/save → validate + backup + rewrite the tickers section,
                             then rebuild output + report
    GET  /scraper-run.html → scraper-run launch page (mode selector + live output)
    GET  /api/scraper-run?mode=... → SSE stream of ``run.py`` output
                                     (full | report_only | override_only)
    GET  /api/scraper-run/status → JSON with running state, pid, exit_code

Binds to 127.0.0.1 by default (single-user, local use). ``--lan`` binds to
0.0.0.0 so other devices on the same network can reach the pages — note that
the editor endpoints are UNAUTHENTICATED: enable only on a trusted LAN.
No external dependencies.
"""

from __future__ import annotations

import argparse
import base64
import hmac
import json
import socket
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from config_loader import load_config
from consolidator import consolidate
from indicator_fields import SUPPORTED_KEYS
from manual_overrides import (
    apply_overrides,
    load_overrides,
    load_validated_overrides,
    save_override,
    validate_entry,
)
from orchestrator import _build_strategy_indicators
from overrides_page import render_overrides_page
from report_html import render as render_report
from tickers_page import render_tickers_page
from scraper_run_page import render_scraper_run_page
from tickers_store import load_tickers, save_tickers

# Path del config: risolto rispetto alla root del progetto (src/..).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = str(PROJECT_ROOT / "config.yaml")

# --- Scraper-run state (in-memory, single-user) ----------------------------
_scrape_state: dict[str, Any] = {
    "running": False, "pid": None, "exit_code": None, "started_at": None,
}

# --- Basic Auth (tutte le pagine e le API) ---------------------------------
# Credenziali di default; per cambiarle creare un file `.server-auth` nella
# root del progetto con una riga "user:password" (git-ignored). Il realm
# dichiara charset UTF-8 (RFC 7617) perché la password può contenere non-ASCII.
DEFAULT_CREDENTIALS = ("admin", "so€uri€€€")
AUTH_REALM = "scraper-system"
AUTH_FILE = ".server-auth"


def load_credentials(path: str | Path | None = None) -> tuple[str, str]:
    """Resolve the server credentials: `.server-auth` file if present, else default."""
    auth_path = Path(path) if path else PROJECT_ROOT / AUTH_FILE
    if auth_path.exists():
        line = auth_path.read_text(encoding="utf-8").strip()
        user, sep, password = line.partition(":")
        if sep and user.strip() and password:
            return user.strip(), password
    return DEFAULT_CREDENTIALS


def is_authorized(header_value: str | None, credentials: tuple[str, str] | None = None) -> bool:
    """Timing-safe check of the `Authorization: Basic ...` header."""
    user, password = credentials or load_credentials()
    expected = f"{user}:{password}".encode("utf-8")
    if not header_value or not header_value.startswith("Basic "):
        return False
    try:
        provided = base64.b64decode(header_value[len("Basic "):].strip(), validate=True)
    except ValueError:  # binascii.Error è sottoclasse di ValueError
        return False
    return hmac.compare_digest(provided, expected)


def rebuild_report(config_path: str) -> None:
    """Apply manual overrides to the existing output.json and re-render.

    Replicates ``run.py --override-only``: no scraping. Loads output.json,
    applies overrides (scraping > manual > missing), rebuilds the indicator
    matrix and renders the HTML report.
    """
    base_dir = Path(config_path).resolve().parent
    config = load_config(config_path)
    output_path = base_dir / config.get("output", {}).get("json_path", "output/output.json")

    if not output_path.exists():
        raise FileNotFoundError(
            f"Output JSON not found at {output_path}. Run the orchestrator first."
        )

    with output_path.open("r", encoding="utf-8") as fh:
        existing = json.load(fh)

    results: dict[str, Any] = {}
    for key, value in existing.items():
        if isinstance(value, dict) and "status" in value:
            results[key] = value

    strategy_cfg = config.get("strategy", {})
    overrides_path = base_dir / strategy_cfg.get("manual_overrides", "manual_overrides.yaml")
    force_keys = strategy_cfg.get("force_manual_overrides", []) or []
    overrides, errors = load_validated_overrides(str(overrides_path))
    for error in errors:
        print(f"  [warn] {error}")

    results = apply_overrides(results, overrides, force_keys=force_keys)

    output = consolidate(results)
    output["strategy_indicators"] = _build_strategy_indicators(config, base_dir, results)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    render_report(config_path)


class OverridesHandler(BaseHTTPRequestHandler):
    """HTTP handler: serves the page, the data API and the report."""

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _require_auth(self) -> bool:
        """Gate unico di autenticazione: True se autorizzato, altrimenti 401.

        Applicato a OGNI richiesta (pagine e API, GET e POST): le rotte
        future sono protette per default.
        """
        if is_authorized(self.headers.get("Authorization")):
            return True
        self.send_response(401)
        self.send_header(
            "WWW-Authenticate", f'Basic realm="{AUTH_REALM}", charset="UTF-8"'
        )
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        if not self._require_auth():
            return
        if self.path == "/":
            # Landing page di default: la dashboard (report.html).
            self.send_response(302)
            self.send_header("Location", "/report.html")
            self.end_headers()
            return
        if self.path == "/overrides.html":
            self._send_html(200, render_overrides_page(load_overrides()))
            return
        if self.path == "/api/data":
            self._send_json(200, {"ok": True, "overrides": load_overrides()})
            return
        if self.path == "/tickers.html":
            self._send_html(200, render_tickers_page(load_tickers(DEFAULT_CONFIG)))
            return
        if self.path == "/api/tickers":
            self._send_json(200, {"ok": True, "tickers": load_tickers(DEFAULT_CONFIG)})
            return
        if self.path == "/scraper-run.html":
            self._send_html(200, render_scraper_run_page())
            return
        if self.path.startswith("/api/scraper-run"):
            if "status" in self.path:
                self._send_json(200, _scrape_state)
            else:
                self._handle_scraper_run_sse()
            return
        if self.path == "/report.html":
            report_path = PROJECT_ROOT / "output" / "report.html"
            if not report_path.exists():
                self._send_html(404, "<h1>Report non trovato</h1><p>Esegui run.py prima.</p>")
                return
            self._send_html(200, report_path.read_text(encoding="utf-8"))
            return
        self._send_html(404, "<h1>404</h1>")

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        if not self._require_auth():
            return
        if self.path == "/api/tickers/save":
            self._handle_tickers_save()
            return
        if self.path != "/api/save":
            self._send_json(404, {"ok": False, "message": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "message": "JSON malformato"})
            return

        if not isinstance(payload, dict):
            self._send_json(400, {"ok": False, "message": "body deve essere un oggetto JSON"})
            return

        key = payload.get("key")
        if key not in SUPPORTED_KEYS:
            self._send_json(400, {"ok": False, "message": f"indicatore non supportato: {key}"})
            return

        enabled = bool(payload.get("enabled", True))
        values: dict[str, Any] = {}
        for field, fspec in _field_specs(key).items():
            raw = payload.get(field)
            if raw is None:
                self._send_json(400, {"ok": False, "message": f"campo mancante: {field}"})
                return
            if fspec["type"] == "number":
                try:
                    values[field] = parse_number(raw)
                except (TypeError, ValueError):
                    self._send_json(400, {"ok": False, "message": f"campo non numerico: {field}"})
                    return
            else:
                values[field] = str(raw).strip()
        try:
            values["stale_after_hours"] = parse_number(payload.get("stale_after_hours", 24))
        except (TypeError, ValueError):
            self._send_json(400, {"ok": False, "message": "stale_after_hours non numerico"})
            return
        values["entered_by"] = "user"
        if payload.get("note"):
            values["note"] = str(payload["note"]).strip()

        # Validazione lato server con la stessa logica del pipeline.
        candidate = {**values, "source": "manual", "enabled": enabled,
                     "fetched_at": datetime.now(timezone.utc).isoformat()}
        try:
            validate_entry(key, candidate)
        except ValueError as error:
            self._send_json(400, {"ok": False, "message": str(error)})
            return

        try:
            save_override(str(_overrides_path()), key, values, enabled=enabled)
            rebuild_report(DEFAULT_CONFIG)
        except Exception as error:  # noqa: BLE001 - errori mostrati all'utente
            self._send_json(500, {"ok": False, "message": f"errore: {error}"})
            return
        self._send_json(200, {"ok": True, "message": "Valore salvato e report rigenerato"})

    def _handle_tickers_save(self) -> None:
        """Validate + backup + persist the tickers section, then re-render."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "message": "JSON malformato"})
            return

        tickers = payload.get("tickers") if isinstance(payload, dict) else None
        if not isinstance(tickers, dict):
            self._send_json(400, {"ok": False,
                                  "message": "body deve contenere 'tickers' (mapping)"})
            return

        try:
            backup_path = save_tickers(DEFAULT_CONFIG, tickers)
            rebuild_report(DEFAULT_CONFIG)
        except ValueError as error:
            # Validazione fallita: nessuna scrittura, nessun backup.
            self._send_json(400, {"ok": False, "message": str(error)})
            return
        except Exception as error:  # noqa: BLE001 - errori mostrati all'utente
            self._send_json(500, {"ok": False, "message": f"errore: {error}"})
            return
        self._send_json(200, {
            "ok": True,
            "message": f"Ticker salvati e report rigenerato (backup: {backup_path.name})",
            "backup": str(backup_path),
        })

    def _handle_scraper_run_sse(self) -> None:
        """Run ``run.py`` with the selected mode and stream output via SSE."""
        if _scrape_state["running"]:
            try:
                msg = "event: error\ndata: Scrape gia' in corso\nevent: done\ndata: -1\n\n"
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()
            except BrokenPipeError:
                pass
            return

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        mode = params.get("mode", ["full"])[0]

        flags = []
        if mode == "report_only":
            flags = ["--report-only"]
        elif mode == "override_only":
            flags = ["--override-only"]

        cmd = [sys.executable, str(PROJECT_ROOT / "run.py"), DEFAULT_CONFIG] + flags

        _scrape_state.update(running=True, pid=None, exit_code=None,
                            started_at=datetime.now(timezone.utc).isoformat())

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            _scrape_state["pid"] = proc.pid
            for line in proc.stdout:
                try:
                    self.wfile.write(f"data: {line.rstrip()}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except BrokenPipeError:
                    break
            proc.wait()
            _scrape_state["exit_code"] = proc.returncode
            try:
                self.wfile.write(
                    f"event: done\ndata: {proc.returncode}\n\n".encode("utf-8")
                )
                self.wfile.flush()
            except BrokenPipeError:
                pass
        except Exception as exc:  # noqa: BLE001
            _scrape_state["exit_code"] = -1
            try:
                self.wfile.write(f"event: error\ndata: {exc}\n\n".encode("utf-8"))
                self.wfile.flush()
            except BrokenPipeError:
                pass
        finally:
            _scrape_state["running"] = False

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        print(f"[overrides] {self.address_string()} - {format % args}")


def _overrides_path() -> Path:
    strategy_cfg = load_config(DEFAULT_CONFIG).get("strategy", {})
    return PROJECT_ROOT / strategy_cfg.get("manual_overrides", "manual_overrides.yaml")


def parse_number(raw: Any) -> float:
    """Parse a number accepting both '.' and ',' as decimal separator."""
    return float(str(raw).strip().replace(",", "."))


def _field_specs(key: str) -> dict[str, Any]:
    from indicator_fields import INDICATOR_FIELDS
    return INDICATOR_FIELDS[key]["fields"]


def _lan_urls(port: int) -> list[str]:
    """Best-effort URLs to reach this server from other LAN devices."""
    urls: list[str] = []
    try:
        # UDP connect: non invia pacchetti, sceglie solo la route primaria.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            urls.append(f"http://{sock.getsockname()[0]}:{port}/")
    except OSError:
        pass
    return urls


def main() -> int:
    parser = argparse.ArgumentParser(description="Dashboard/overrides/tickers local server")
    parser.add_argument("-p", "--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--lan",
        action="store_true",
        help="accessibile dagli altri dispositivi della LAN (bind 0.0.0.0); "
        "gli endpoint di scrittura NON sono autenticati: usare solo su rete fidata",
    )
    args = parser.parse_args()
    host = "0.0.0.0" if args.lan else args.host
    server = ThreadingHTTPServer((host, args.port), OverridesHandler)
    print(f"Serving on http://{args.host}:{args.port}/ (Ctrl+C per fermare)")
    if args.lan:
        for url in _lan_urls(args.port):
            print(f"  LAN: {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
