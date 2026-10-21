"""HTTP plumbing: request object, JSON responses, error mapping and the threaded server.

Every request gets its own SQLite connection (opened after routing and
authentication, closed before the response is written) because connections
must not be shared across the server's threads. Handlers return
``(status, payload)``; a ``LedgerError`` becomes ``to_dict()`` with its
``status``; anything else is logged and answered with a generic 500.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, BinaryIO
from urllib.parse import parse_qs, urlsplit

from ledger import __version__
from ledger.api.auth import authenticate, require
from ledger.api.router import MethodNotAllowed, Router
from ledger.core import db
from ledger.core.config import ApiToken, Settings
from ledger.core.errors import InvalidInput, LedgerError, PayloadTooLarge, Unauthorized
from ledger.core.log import get_logger

log = get_logger("api.server")


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: Message
    params: dict[str, Any]
    settings: Settings
    conn: sqlite3.Connection
    token: ApiToken | None
    stream: BinaryIO = field(repr=False)

    def one(self, name: str) -> str | None:
        """A single-valued query parameter; ``None`` when absent, 400 when repeated."""
        values = self.query.get(name, [])
        if len(values) > 1:
            raise InvalidInput(f"query parameter {name!r} given more than once", parameter=name)
        return values[0] if values else None

    def body(self, limit: int) -> bytes:
        """The request body; requires ``Content-Length`` (no chunked uploads) and enforces ``limit``."""
        if self.headers.get("Transfer-Encoding"):
            raise InvalidInput("chunked transfer encoding is not supported; send Content-Length")
        raw = (self.headers.get("Content-Length") or "").strip()
        if not raw.isdigit():
            raise InvalidInput("Content-Length header required")
        length = int(raw)
        if length > limit:
            raise PayloadTooLarge(f"body of {length} bytes exceeds the limit of {limit}", limit=limit)
        return self.stream.read(length) if length else b""

    def json(self, limit: int = 64 * 1024) -> Any:
        try:
            return json.loads(self.body(limit).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidInput(f"body is not valid JSON: {exc}") from exc


class Handler(BaseHTTPRequestHandler):
    server: LedgerServer
    server_version = f"ledger/{__version__}"

    def version_string(self) -> str:
        return self.server_version  # no Python version in the Server header

    def do_GET(self) -> None:
        self._dispatch()

    do_POST = do_PUT = do_PATCH = do_DELETE = do_GET

    def _dispatch(self) -> None:
        started = time.monotonic()
        url = urlsplit(self.path)
        token: ApiToken | None = None
        headers: dict[str, str] = {}
        try:
            route, params = self.server.router.resolve(self.command, url.path)
            if route.role is not None:
                token = authenticate(self.headers.get("Authorization"), self.server.settings.tokens)
                require(token, route.role)
            conn = db.open_db(self.server.settings)
            try:
                request = Request(
                    self.command, url.path, parse_qs(url.query), self.headers, params,
                    self.server.settings, conn, token, self.rfile,
                )
                status, payload = route.handler(request)
            finally:
                conn.close()
        except LedgerError as exc:
            status, payload = exc.status, exc.to_dict()
            if isinstance(exc, MethodNotAllowed):
                headers["Allow"] = ", ".join(exc.details["allowed"])
            elif isinstance(exc, Unauthorized):
                headers["WWW-Authenticate"] = 'Bearer realm="ledger"'
        except Exception:
            log.exception("api.error", extra={"method": self.command, "path": url.path})
            status, payload = 500, {"error": "internal_error", "message": "internal server error"}
        self._send(status, payload, headers)
        log.info("api.request", extra={
            "method": self.command, "path": url.path, "status": status,
            "ms": round((time.monotonic() - started) * 1000, 1), "token": token.name if token else None,
        })

    def _send(self, status: int, payload: Any, headers: dict[str, str]) -> None:
        try:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError):
            log.exception("api.encode_error", extra={"path": urlsplit(self.path).path})
            status, body = 500, b'{"error": "internal_error", "message": "internal server error"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        pass  # _dispatch logs api.request with more context

    def log_message(self, format: str, *args: Any) -> None:
        log.warning("api.http", extra={"detail": format % args, "client": self.client_address[0]})


class LedgerServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], settings: Settings, router: Router) -> None:
        self.settings = settings
        self.router = router
        super().__init__(address, Handler)


def make_server(settings: Settings, *, host: str | None = None, port: int | None = None) -> LedgerServer:
    """A bound server; ``port=0`` picks a free port (``server.server_address[1]``)."""
    from ledger.api.routes import build_router

    address = (settings.api_host if host is None else host, settings.api_port if port is None else port)
    return LedgerServer(address, settings, build_router())
