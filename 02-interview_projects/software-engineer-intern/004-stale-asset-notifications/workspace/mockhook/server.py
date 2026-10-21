"""Dev-only webhook receiver (docs/architecture.md §4.7): one JSON line per delivery.

``POST /hooks/<name>`` logs to ``MOCKHOOK_LOG`` and answers 200, or 401 on a
bad signature when ``MOCKHOOK_SECRET`` is set; ``GET /hooks`` returns the
last 50 lines. It plays the customer, so it verifies with its own code.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from collections import deque
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY_BYTES = 1024 * 1024
TOLERANCE_SECONDS = 300


def signature_ok(secret: str, body: bytes, header: str, now: float) -> bool:
    fields: dict[str, list[str]] = {}
    for part in header.split(","):
        name, _, value = part.strip().partition("=")
        fields.setdefault(name, []).append(value)
    timestamp = (fields.get("t") or [""])[0]
    if not timestamp.isdigit() or abs(now - int(timestamp)) > TOLERANCE_SECONDS:
        return False  # malformed, replayed or from the future
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in fields.get("v1", []))


class MockhookServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, log_path: Path, secret: str = "", clock_offset: float = 0.0):
        super().__init__(address, Handler)
        self.log_path, self.secret = log_path, secret
        self.clock_offset = clock_offset  # seconds; follows Atlas's dev clock (ATLAS_NOW)
        self.lock = threading.Lock()
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict) -> None:
        with self.lock, self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")

    def tail(self, count: int = 50) -> list[dict]:
        with self.lock:
            if not self.log_path.exists():
                return []
            with self.log_path.open(encoding="utf-8") as fh:
                return [json.loads(line) for line in deque(fh, maxlen=count) if line.strip()]


class Handler(BaseHTTPRequestHandler):
    server: MockhookServer
    server_version = "mockhook/1"

    def _reply(self, status: int, payload) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/hooks":
            self._reply(200, self.server.tail())
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self.path.startswith("/hooks/") or self.path == "/hooks/":
            return self._reply(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            return self._reply(413, {"error": "body too large"})
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except ValueError:
            body = raw.decode("utf-8", "replace")
        signature = self.headers.get("X-Atlas-Signature", "")
        record = {"received_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"), "path": self.path,
                  "event": self.headers.get("X-Atlas-Event", ""), "signature": signature, "body": body,
                  "delivery": self.headers.get("X-Atlas-Delivery", "")}
        if self.server.secret:
            now = time.time() + self.server.clock_offset
            record["signature_ok"] = signature_ok(self.server.secret, raw, signature, now)
        self.server.append(record)
        if record.get("signature_ok") is False:
            return self._reply(401, {"ok": False, "error": "bad signature"})
        return self._reply(200, {"ok": True})


def main() -> None:
    port = int(os.environ.get("MOCKHOOK_PORT", "9000"))
    log_path = Path(os.environ.get("MOCKHOOK_LOG", "var/mockhook/deliveries.jsonl"))
    start = os.environ.get("ATLAS_NOW", "")
    offset = datetime.fromisoformat(start).timestamp() - time.time() if start else 0.0
    secret = os.environ.get("MOCKHOOK_SECRET", "")
    server = MockhookServer(("0.0.0.0", port), log_path, secret, offset)  # noqa: S104
    print(f"mockhook listening on :{port}, logging to {log_path}", flush=True)
    server.serve_forever()
