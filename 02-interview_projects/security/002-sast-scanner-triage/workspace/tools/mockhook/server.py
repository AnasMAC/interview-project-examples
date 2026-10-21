#!/usr/bin/env python3
"""Local webhook receiver for development and tests.

Everything the product sends to a webhook URL can land here instead of on a
real endpoint. By default the receiver accepts whatever it gets and appends one
JSON object per delivery to ``--log`` (default ``var/mockhook/deliveries.jsonl``);
with ``MOCKHOOK_STRICT=1`` (or ``--strict``) it verifies
``X-Bellpost-Signature: t=<unix>,v1=<hex hmac-sha256(secret, "<t>.<raw body>")>``,
enforces the 300 second tolerance and answers 401 on a mismatch.

This is a test double, not product code: it never verifies anything unless
strict mode is on, and it accepts deliveries on any path (the convention is
``/hooks/<tenant>``).

Usage::

    python tools/mockhook/server.py --port 8900 --log var/mockhook/deliveries.jsonl
    MOCKHOOK_STRICT=1 MOCKHOOK_SECRET=DEMO-whsec-brp-0001 python tools/mockhook/server.py
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

DEFAULT_PORT = 8900
DEFAULT_LOG = "var/mockhook/deliveries.jsonl"
DEFAULT_SECRET = "DEMO-whsec-local-mockhook"
SIGNATURE_TOLERANCE_SECONDS = 300
MAX_BODY_BYTES = 5 * 1024 * 1024


def parse_signature(header: str | None) -> tuple[int | None, list[str]]:
    """Split ``t=<unix>,v1=<hex>`` into its timestamp and v1 digests."""
    if not header:
        return None, []
    timestamp: int | None = None
    digests: list[str] = []
    for part in header.split(","):
        name, _, value = part.strip().partition("=")
        if name == "t":
            try:
                timestamp = int(value)
            except ValueError:
                return None, []
        elif name == "v1" and value:
            digests.append(value)
    return timestamp, digests


def verify_signature(
    secret: str,
    header: str | None,
    body: bytes,
    *,
    now: float | None = None,
    tolerance: int | None = SIGNATURE_TOLERANCE_SECONDS,
) -> bool:
    """Check a Bellpost signature header against the raw body."""
    timestamp, digests = parse_signature(header)
    if timestamp is None or not digests:
        return False
    if tolerance is not None:
        current = time.time() if now is None else now
        if abs(current - timestamp) > tolerance:
            return False
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return any(hmac.compare_digest(expected, digest) for digest in digests)


def describe_event(body: bytes) -> str | None:
    """Best-effort read of the ``event`` field of a JSON payload."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict) and isinstance(payload.get("event"), str):
        return payload["event"]
    return None


def append_record(log_path: Path, record: dict[str, Any]) -> None:
    """Append one delivery record as a JSON line."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def read_records(log_path: Path) -> list[dict[str, Any]]:
    """Read back every delivery record (used by tests and the /deliveries route)."""
    if not log_path.exists():
        return []
    records: list[dict[str, Any]] = []
    with log_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


class MockhookServer(ThreadingHTTPServer):
    """Threading HTTP server carrying the mockhook configuration."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], *, log_path: Path, strict: bool, secret: str):
        super().__init__(address, MockhookHandler)
        self.log_path = log_path
        self.strict = strict
        self.secret = secret


class MockhookHandler(BaseHTTPRequestHandler):
    server_version = "mockhook/1.0"
    protocol_version = "HTTP/1.1"

    @property
    def config(self) -> MockhookServer:
        return cast(MockhookServer, self.server)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            self._respond(413, {"ok": False, "error": "body too large"})
            return
        body = self.rfile.read(length) if length else b""

        signature = self.headers.get("X-Bellpost-Signature")
        strict = self.config.strict
        signature_ok: bool | None = None
        if strict:
            signature_ok = verify_signature(self.config.secret, signature, body)

        record: dict[str, Any] = {
            "received_at": time.time(),
            "path": self.path,
            "event": describe_event(body),
            "strict": strict,
            "signature": signature,
            "signature_ok": signature_ok,
            "body_sha256": hashlib.sha256(body).hexdigest(),
            "body": body.decode("utf-8", errors="replace"),
        }

        if strict and not signature_ok:
            record["status"] = 401
            append_record(self.config.log_path, record)
            self._respond(401, {"ok": False, "signature_ok": False, "error": "signature"})
            return

        record["status"] = 200
        append_record(self.config.log_path, record)
        self._respond(
            200,
            {
                "ok": True,
                "signature_ok": signature_ok,
                "event": record["event"],
                "received_at": record["received_at"],
            },
        )

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.startswith("/healthz"):
            self._respond(200, {"ok": True, "strict": self.config.strict})
            return
        if self.path.startswith("/deliveries"):
            records = read_records(self.config.log_path)
            self._respond(200, {"ok": True, "count": len(records), "deliveries": records})
            return
        self._respond(404, {"ok": False, "error": "not found"})

    def _respond(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"mockhook {self.address_string()} {format % args}", flush=True)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local Bellpost webhook receiver")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MOCKHOOK_PORT") or DEFAULT_PORT),
        help="port to bind on 127.0.0.1 (default: MOCKHOOK_PORT or 8900)",
    )
    parser.add_argument(
        "--log",
        default=os.environ.get("MOCKHOOK_LOG") or DEFAULT_LOG,
        help="JSONL file deliveries are appended to (default: %(default)s)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=_env_flag("MOCKHOOK_STRICT"),
        help="verify the X-Bellpost-Signature header (default: MOCKHOOK_STRICT)",
    )
    parser.add_argument(
        "--secret",
        default=os.environ.get("MOCKHOOK_SECRET") or DEFAULT_SECRET,
        help="signing secret used in strict mode (default: MOCKHOOK_SECRET)",
    )
    args = parser.parse_args(argv)

    server = MockhookServer(
        ("127.0.0.1", args.port),
        log_path=Path(args.log),
        strict=bool(args.strict),
        secret=args.secret,
    )
    print(f"mockhook listening on 127.0.0.1:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
