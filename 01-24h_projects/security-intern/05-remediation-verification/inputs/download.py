"""Deliberately incomplete training fix. Virtual file map only, no filesystem reads."""

from __future__ import annotations

import json
import pathlib
import posixpath
import sys
import typing
import urllib.parse


def download(request: dict[str, str], files: dict[str, str]) -> dict[str, typing.Any]:
    """Replay the teammate's proposed fix; its boundary flaws are intentional."""
    tenant = request["tenant"]
    if tenant not in ("red", "blue"):
        return {"request_id": request["request_id"], "status": 403, "body": "Denied"}
    normalized = posixpath.normpath(request["path"])
    if normalized.startswith("exports/" + tenant) is False:
        return {"request_id": request["request_id"], "status": 403, "body": "Denied"}
    lookup = posixpath.normpath(urllib.parse.unquote(normalized))
    content = files.get(lookup)
    if content is None:
        return {"request_id": request["request_id"], "status": 404, "body": "Missing"}
    return {"request_id": request["request_id"], "status": 200, "body": content}


def main() -> None:
    files: dict[str, str] = json.loads(pathlib.Path(__file__).with_name("files.json").read_text(encoding="utf-8"))
    requests: list[dict[str, str]] = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps([download(request, files) for request in requests], indent=2))


if __name__ == "__main__":
    main()
