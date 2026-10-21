"""Time the scorecard and the CSV export on the seeded dev database.

    make bench                       # or: python scripts/bench.py --repeat 5
    make bench BENCH_ARGS="--json var/bench/latest.json"

Requests go through the Flask test client (no gunicorn, no network) with the
seeded ``security-review`` key, and the window ends at the seed anchor so the
numbers do not drift with the wall clock. Compare runs on the same machine
and the same ``--scale`` only.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import sys
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from gatekeeper.core.app import create_app  # noqa: E402
from gatekeeper.core.config import get_settings  # noqa: E402
from gatekeeper.core.db import transaction  # noqa: E402
from gatekeeper.core.tables import evaluations  # noqa: E402
from gatekeeper.seed.data import ANCHOR, seeded_key  # noqa: E402

UNTIL = quote(ANCHOR.isoformat())
CASES = (
    ("scorecard, all teams, 28 days", f"/v1/reports/scorecard?days=28&until={UNTIL}"),
    ("scorecard, all teams, 84 days", f"/v1/reports/scorecard?days=84&until={UNTIL}"),
    ("scorecard, payments-api, 84 days",
     f"/v1/reports/scorecard?team=payments-api&days=84&until={UNTIL}"),
    ("export.csv, all teams, 28 days", f"/v1/reports/export.csv?days=28&until={UNTIL}"),
    ("export.csv, all teams, 84 days", f"/v1/reports/export.csv?days=84&until={UNTIL}"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--json", type=Path, help="also write the results to this file")
    args = parser.parse_args()

    app = create_app(dataclasses.replace(get_settings(), log_level="WARNING"))
    client = app.test_client()
    headers = {"Authorization": f"Bearer {seeded_key('security-review')}"}
    if client.get("/v1/whoami", headers=headers).status_code != 200:
        print("the seeded security-review key does not work: run `make seed` first",
              file=sys.stderr)
        return 1
    with transaction() as conn:
        total = conn.execute(select(func.count()).select_from(evaluations)).scalar()
    print(f"{total:,} evaluations in the database, {args.repeat} runs per case\n")

    results = []
    print(f"{'case':<36} {'median ms':>10} {'min ms':>9} {'max ms':>9} {'bytes':>12}")
    for name, url in CASES:
        timings, size = [], 0
        for _ in range(args.repeat):
            started = time.perf_counter()
            response = client.get(url, headers=headers)
            timings.append((time.perf_counter() - started) * 1000)
            if response.status_code != 200:
                print(f"{name}: HTTP {response.status_code} {response.get_data(as_text=True)}")
                return 1
            size = len(response.get_data())
        row = {"case": name, "median_ms": round(statistics.median(timings), 1),
               "min_ms": round(min(timings), 1), "max_ms": round(max(timings), 1), "bytes": size}
        results.append(row)
        print(f"{name:<36} {row['median_ms']:>10} {row['min_ms']:>9} {row['max_ms']:>9} "
              f"{size:>12,}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"evaluations": total, "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
