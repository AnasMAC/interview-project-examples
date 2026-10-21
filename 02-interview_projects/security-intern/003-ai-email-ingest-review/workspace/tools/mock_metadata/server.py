#!/usr/bin/env python3
"""Local stand-in for the cloud instance-metadata service.

The security work recorded in ``docs/security-notes.md`` checks that outbound
webhook delivery cannot reach link-local addresses; this service answers the
same paths a real metadata endpoint does, but every value is a ``DEMO-``
placeholder that grants nothing. It binds to 127.0.0.1 only and is never
deployed.

Usage::

    python tools/mock_metadata/server.py --port 8901

Answers::

    GET /latest/meta-data/
    GET /latest/meta-data/iam/security-credentials/
    GET /latest/meta-data/iam/security-credentials/bellpost-role
    GET /latest/api/token
"""

from __future__ import annotations

import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

DEFAULT_PORT = 8901
DEMO_ROLE = "bellpost-role"
DEMO_CREDENTIALS: dict[str, Any] = {
    "Code": "Success",
    "LastUpdated": "2026-05-11T08:00:00Z",
    "Type": "AWS-HMAC",
    "AccessKeyId": "DEMO-AKIA-BELLPOST",
    "SecretAccessKey": "DEMO-not-a-real-secret",
    "Token": "DEMO-mock-session-token",
    "Expiration": "2026-05-11T14:00:00Z",
}


class MetadataHandler(BaseHTTPRequestHandler):
    server_version = "mock-metadata/1.0"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = self.path.split("?", 1)[0]
        if path in ("/latest/meta-data/", "/latest/meta-data"):
            self._text("iam/\n")
            return
        if path in (
            "/latest/meta-data/iam/",
            "/latest/meta-data/iam",
            "/latest/meta-data/iam/security-credentials",
            "/latest/meta-data/iam/security-credentials/",
        ):
            self._text(DEMO_ROLE)
            return
        if path == f"/latest/meta-data/iam/security-credentials/{DEMO_ROLE}":
            self._json(DEMO_CREDENTIALS)
            return
        if path == "/latest/api/token":
            self._text("DEMO-IMDS-TOKEN")
            return
        if path == "/":
            self._text(
                "mock metadata service (local stand-in)\n"
                "paths: /latest/meta-data/, /latest/meta-data/iam/security-credentials/"
                f"{DEMO_ROLE}, /latest/api/token\n"
                "all values are DEMO- placeholders\n"
            )
            return
        self._text("not found\n", status=404)

    def do_PUT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        # IMDSv2 style token request; the real service takes a PUT.
        if self.path.split("?", 1)[0] == "/latest/api/token":
            self._text("DEMO-IMDS-TOKEN")
            return
        self._text("not found\n", status=404)

    def _text(self, body: str, *, status: int = 200) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        print(
            f"mock-metadata {time.strftime('%H:%M:%S')} {self.address_string()} {format % args}",
            flush=True,
        )


class MetadataServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local instance-metadata stand-in (DEMO values)")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MOCK_METADATA_PORT") or DEFAULT_PORT),
        help="port to bind on 127.0.0.1 (default: MOCK_METADATA_PORT or 8901)",
    )
    args = parser.parse_args(argv)

    server = MetadataServer(("127.0.0.1", args.port), MetadataHandler)
    print(f"mock_metadata listening on 127.0.0.1:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
