"""Exercise scaffold: CLI I/O works; the assessed feature is intentionally absent."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import typing


def search_assets(payload: dict[str, typing.Any], arguments: argparse.Namespace) -> dict[str, typing.Any]:
    """Implement the candidate README contract here; refactor freely."""
    raise NotImplementedError("STARTER: implement search_assets; no feature output was produced")


def main() -> int:
    parser = argparse.ArgumentParser(description="Search synthetic assets locally with deterministic pagination.")
    parser.add_argument("--input", default="inputs/primary.json", help="UTF-8 fixture JSON")
    parser.add_argument("--tenant", default="north")
    parser.add_argument("--query", default="")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--status", choices=["active", "archived"])
    parser.add_argument("--min-risk", type=int, default=0)
    parser.add_argument("--sort", choices=["name", "risk"], default="name")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=2)
    arguments = parser.parse_args()
    try:
        payload = json.loads(pathlib.Path(arguments.input).read_text(encoding="utf-8"))
        if isinstance(payload, dict) is False:
            raise ValueError("input must be a JSON object")
        result = search_assets(payload, arguments)
        print(json.dumps(result, indent=2, sort_keys=True))
    except NotImplementedError as error:
        print(str(error), file=sys.stderr)
        return 3
    except (OSError, UnicodeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
