"""Exercise scaffold: CLI I/O works; the assessed feature is intentionally absent."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import typing


def reduce_jobs(payload: dict[str, typing.Any], arguments: argparse.Namespace) -> dict[str, typing.Any]:
    """Implement the candidate README contract here; refactor freely."""
    raise NotImplementedError("STARTER: implement reduce_jobs; no feature output was produced")


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay job events without running scans or sleeping.")
    parser.add_argument("--input", default="inputs/primary.json", help="UTF-8 fixture JSON")
    arguments = parser.parse_args()
    try:
        payload = json.loads(pathlib.Path(arguments.input).read_text(encoding="utf-8"))
        if isinstance(payload, dict) is False:
            raise ValueError("input must be a JSON object")
        result = reduce_jobs(payload, arguments)
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
