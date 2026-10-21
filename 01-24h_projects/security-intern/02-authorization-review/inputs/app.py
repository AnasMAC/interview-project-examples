"""Deliberately vulnerable authorization training app; no server or network."""

from __future__ import annotations

import copy
import json
import pathlib
import sys
import typing

STATE_PATH = pathlib.Path(__file__).with_name("state.json")


def load_state() -> dict[str, typing.Any]:
    return typing.cast(dict[str, typing.Any], json.loads(STATE_PATH.read_text(encoding="utf-8")))


def update_task(state: dict[str, typing.Any], request: dict[str, str]) -> dict[str, typing.Any]:
    """Apply a status update; policy omissions are intentional training flaws."""
    actor = state["actors"].get(request["actor_id"])
    task = state["tasks"].get(request["task_id"])
    if actor is None:
        status, message = 401, "Unknown identity"
    elif task is None:
        status, message = 404, "Missing task"
    elif request["status"] not in ("open", "done"):
        status, message = 400, "Invalid status"
    elif actor["role"] not in ("editor", "admin"):
        status, message = 403, "Role denied"
    elif actor["role"] != "admin" and actor["tenant"] != task["tenant"]:
        status, message = 403, "Tenant denied"
    else:
        task["status"] = request["status"]
        status, message = 200, "Updated"
    return {"request_id": request["request_id"], "status": status, "message": message}


def main() -> None:
    state = copy.deepcopy(load_state())
    requests: list[dict[str, str]] = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    responses = [update_task(state, request) for request in requests]
    print(json.dumps({"responses": responses, "tasks": state["tasks"]}, indent=2))


if __name__ == "__main__":
    main()
