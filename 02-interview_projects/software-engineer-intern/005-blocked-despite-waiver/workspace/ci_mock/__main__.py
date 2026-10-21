"""``python -m ci_mock``: stdlib receiver for Gatekeeper callbacks (compose ``ci-mock``).

Accepts ``POST /callbacks/<team>/<service>`` and ``POST /notify/<team>``,
appends one JSON line per request to ``CI_MOCK_LOG`` and answers 204.
Deliberately independent of the ``gatekeeper`` package: it checks the
signature the way a CI system would, from the documented wire format.

``CI_MOCK_SECRET`` turns verification on: either one secret for every team or
``<team>=<secret>,...``. A bad or stale signature is logged and answered 401
so Gatekeeper retries. Without it, ``signature_valid`` is logged as null.
Timestamps are compared with ``GATE_NOW`` when compose pins Gatekeeper's dev
clock, else with the wall clock.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import signal
import sys
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

TOLERANCE_S = 300
_write_lock = Lock()


def parse_secrets(raw: str) -> dict[str, str] | str | None:
    raw = raw.strip()
    if not raw:
        return None
    if "=" not in raw:
        return raw
    pairs = (item.split("=", 1) for item in raw.split(",") if item.strip())
    return {team.strip(): secret.strip() for team, secret in pairs}


def _now() -> float:
    raw = os.environ.get("GATE_NOW", "").strip()
    return datetime.fromisoformat(raw).timestamp() if raw else time.time()


def signature_valid(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    if not timestamp.isdigit() or abs(_now() - int(timestamp)) > TOLERANCE_S:
        return False
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return hmac.compare_digest("sha256=" + expected.hexdigest(), signature)


class Handler(BaseHTTPRequestHandler):
    server_version = "ci-mock/1.0"
    log_path: Path = Path("var/ci-mock/callbacks.jsonl")
    secrets: dict[str, str] | str | None = None

    def _secret_for(self, team: str) -> str | None:
        if isinstance(self.secrets, dict):
            return self.secrets.get(team)
        return self.secrets

    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        self._answer(200 if self.path == "/healthz" else 404)

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        parts = self.path.strip("/").split("/")
        if len(parts) < 2 or parts[0] not in ("callbacks", "notify"):
            self._answer(404)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        secret = self._secret_for(parts[1])
        valid = None
        if secret is not None:
            valid = signature_valid(secret, self.headers.get("X-Gatekeeper-Timestamp", ""), body,
                                    self.headers.get("X-Gatekeeper-Signature", ""))
        try:
            payload = json.loads(body)
        except ValueError:
            payload = None
        entry = {
            "received_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "path": self.path,
            "event": self.headers.get("X-Gatekeeper-Event"),
            "delivery": self.headers.get("X-Gatekeeper-Delivery"),
            "timestamp": self.headers.get("X-Gatekeeper-Timestamp"),
            "signature_valid": valid,
            "body": payload,
        }
        with _write_lock, self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        self._answer(401 if valid is False else 204)

    def _answer(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return  # every request is already a JSON line in the log file


def make_server(port: int, log_path: Path, secrets: dict[str, str] | str | None
                ) -> ThreadingHTTPServer:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = type("ConfiguredHandler", (Handler,), {"log_path": log_path, "secrets": secrets})
    return ThreadingHTTPServer(("0.0.0.0", port), handler)  # noqa: S104 - compose network only


def main() -> int:
    port = int(os.environ.get("CI_MOCK_PORT", "9100"))
    log_path = Path(os.environ.get("CI_MOCK_LOG", "var/ci-mock/callbacks.jsonl"))
    server = make_server(port, log_path, parse_secrets(os.environ.get("CI_MOCK_SECRET", "")))
    print(json.dumps({"msg": "ci_mock.listening", "port": port, "log": str(log_path),
                      "verify": server.RequestHandlerClass.secrets is not None}), flush=True)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # PID 1 ignores SIGTERM otherwise
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
