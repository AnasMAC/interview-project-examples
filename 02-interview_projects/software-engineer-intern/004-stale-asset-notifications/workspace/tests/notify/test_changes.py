from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from atlas.assets.models import Asset
from atlas.notify.changes import changed_asset_ids, window_start
from tests.factories import TODAY, make_asset, make_change

TORONTO = ZoneInfo("America/Toronto")
# Noon on 2026-11-01 in Toronto, the day DST ended (EDT -> EST at 06:00Z).
DST_END_NOON = datetime(2026, 11, 1, 17, 0, tzinfo=UTC)
pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("now", [DST_END_NOON, DST_END_NOON.astimezone(TORONTO)])
def test_window_is_24_elapsed_hours_across_dst_end(org, now):
    start = window_start(org, now=now)
    assert start == datetime(2026, 10, 31, 17, 0, tzinfo=UTC)  # 13:00 EDT, not 12:00 (a 25 h window)
    assert now - start == timedelta(hours=24)


def test_window_defaults_to_the_clock_and_rejects_bad_input(org):
    assert window_start(org, hours=1) == TODAY - timedelta(hours=1)
    with pytest.raises(ValueError, match="aware"):
        window_start(org, now=datetime(2026, 11, 1, 12, 0))
    with pytest.raises(ValueError, match="positive"):
        window_start(org, hours=0)


def test_changed_asset_ids_over_dst_end(org, other_org, frozen_clock):
    frozen_clock.freeze(DST_END_NOON)
    since = window_start(org)
    edge, stale, foreign = make_asset(org), make_asset(org), make_asset(other_org, Asset.Kind.IP)
    make_change(edge, occurred_at=since)
    make_change(edge, kind="updated", occurred_at=since + timedelta(hours=3))
    make_change(stale, occurred_at=since - timedelta(minutes=30))  # inside a wall-clock "since noon" window
    make_change(foreign, occurred_at=since + timedelta(hours=1))
    assert list(changed_asset_ids(org, since)) == [edge.id]
    assert list(Asset.objects.filter(id__in=changed_asset_ids(org, since))) == [edge]
