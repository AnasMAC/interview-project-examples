"""Time the asset search API and the dashboard list on seeded data, in process.

    make bench                                        # all orgs, 5 runs per case
    docker compose run --rm web python scripts/bench.py --org quillstone-media --repeat 9

Requests go through Django's test client against the dev database: no server, no host port.
Seed first (`make seed`; `make seed SEED_ARGS="--reset --scale 8"` for Quillstone at ~40k
assets, REQ-0219) and create the dashboard user (`python manage.py create_demo_user`).
Numbers are wall-clock milliseconds including rendering; compare runs on the same machine.
"""

import argparse
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "atlas.settings.dev")
os.environ.setdefault("ATLAS_API_RATE", "100000/min")  # the bench is not what the throttle is for


def measure(client, url: str, repeat: int) -> tuple:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    times = []
    for _ in range(repeat):
        with CaptureQueriesContext(connection) as queries:
            start = time.perf_counter()
            response = client.get(url)
            body = b"".join(response.streaming_content) if response.streaming else response.content
            times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times), max(times), len(queries), response.status_code, len(body)


def deep_cursor(client, pages: int) -> tuple[str, int]:
    """The URL of page ``pages + 1`` (100 assets a page, or the last page), following ``next``."""
    url, page = "/api/v1/assets/?page_size=100", 1
    while page <= pages:
        response = client.get(url)
        if response.status_code != 200 or not response.json().get("next"):
            break
        url, page = response.json()["next"], page + 1
    return url, page


def main() -> int:
    import django

    django.setup()
    from django.contrib.auth import get_user_model
    from django.test import Client

    from atlas.assets.models import Asset
    from atlas.core.management.commands.seed import PROFILES
    from atlas.core.models import Org

    parser = argparse.ArgumentParser(description="Time asset search and the dashboard list.")
    parser.add_argument("--org", action="append", choices=sorted(PROFILES), help="repeatable; default all")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--depth", type=int, default=50, help="pages of 100 before the deep-cursor case")
    args = parser.parse_args()
    demo = get_user_model().objects.filter(username="demo").first()
    if not Org.objects.exists() or demo is None:
        print("No seeded data: run `make seed` and `python manage.py create_demo_user` first.")
        return 1
    print(f"{'org':<18}{'case':<22}{'assets':>8}{'median ms':>11}{'max ms':>9}{'queries':>9}{'status':>8}"
          f"{'KiB':>8}")
    for slug in args.org or list(PROFILES):
        org = Org.objects.get(slug=slug)
        assets = Asset.objects.for_org(org).filter(archived_at__isnull=True).count()
        api = Client(HTTP_HOST="localhost", HTTP_AUTHORIZATION=f"Bearer {PROFILES[slug].api_key}")
        dashboard = Client(HTTP_HOST="localhost")
        dashboard.force_login(demo)
        deep_url, page = deep_cursor(api, args.depth)
        cases = [
            ("api first page", api, "/api/v1/assets/"),
            ("api filtered", api, "/api/v1/assets/?kind=ip&exposure=any"),
            (f"api cursor page {page}", api, deep_url),
            ("dashboard list", dashboard, f"/assets/?org={slug}"),
            ("dashboard filtered", dashboard, f"/assets/?org={slug}&kind=ip&exposure=any"),
            ("csv download", dashboard, f"/assets.csv?org={slug}"),
        ]
        for name, client, url in cases:
            median, worst, queries, status, size = measure(client, url, args.repeat)
            print(f"{slug:<18}{name:<22}{assets:>8,}{median:>11.1f}{worst:>9.1f}{queries:>9}{status:>8}"
                  f"{size / 1024:>8.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
