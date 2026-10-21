"""Deliberately vulnerable, in-memory assessment model. No network or server."""

from __future__ import annotations

import html
import json
import pathlib
import sys
import typing

REPORTS = {"r-red": {"tenant": "red", "body": "Red forecast: 120"}, "r-blue": {"tenant": "blue", "body": "Blue forecast: 340"}}
SESSIONS = {"red-reader": "red", "blue-reader": "blue"}


def respond(request: dict[str, typing.Any]) -> dict[str, typing.Any]:
    """Replay a simplified request; training flaws are intentional."""
    route = request["route"]
    headers = {"Content-Type": "text/html", "X-Frame-Options": "DENY"}
    if route == "/preview":
        body = "<p>" + html.escape(request.get("query", ""), quote=True) + "</p>"
        status = 200
    elif route == "/reports":
        tenant = SESSIONS.get(request.get("session", ""))
        report = REPORTS.get(request.get("report_id", ""))
        if tenant is None:
            status, body = 401, "Sign in"
        elif report is None:
            status, body = 404, "Missing"
        else:
            status, body = 200, report["body"]
    else:
        status, body = 404, "Missing"
    return {"request_id": request["request_id"], "status": status, "headers": headers, "body": body}


def main() -> None:
    requests: list[dict[str, typing.Any]] = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps([respond(request) for request in requests], indent=2))


if __name__ == "__main__":
    main()
