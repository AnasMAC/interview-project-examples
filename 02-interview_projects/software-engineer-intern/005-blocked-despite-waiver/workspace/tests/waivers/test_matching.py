from __future__ import annotations

from datetime import timedelta

import pytest

from gatekeeper.core.contracts import RuleResult
from gatekeeper.waivers.service import apply_waivers
from gatekeeper.waivers.versions import in_range, parse_range
from tests.factories import TODAY

BLOCKED = RuleResult("dependency.max_severity", "block", "ledgerkit 2.4.1: MBSA-2026-0141 is "
                     "critical (max high)", {"violations": []})
PASSED = RuleResult("secrets.allowed", "pass", "0 secret findings (max 0)")


@pytest.mark.parametrize(("version", "version_range", "expected"), [
    ("4.12", ">=4.12.0,<4.13.0", True),
    ("4.12.0", "==4.12", True),
    ("4.13.0-rc.1", ">=4.12.0,<4.13.0", True),
    ("4.13.0", ">=4.12.0,<4.13.0", False),
    ("4.13.0-rc.10", ">4.13.0-rc.9", True),
    ("4.9.9", ">=4.10.0", False),
    ("v4.12.1+build.7", "> 4.12", True),
    ("nightly", ">=1.0", False),
])
def test_version_ranges(version, version_range, expected):
    assert in_range(version, version_range) is expected


@pytest.mark.parametrize("bad", ["", "~4.12", ">=4.x", ">=4.12;<5"])
def test_malformed_ranges_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_range(bad)


@pytest.fixture
def payments(factory):
    return factory.service(factory.team("payments-api"), "payments-api")


@pytest.fixture
def apply(conn, payments):
    def _apply(version="4.12.0"):
        return apply_waivers(conn, team_id=payments.team_id, service_id=payments.id,
                             version=version, results=[BLOCKED, PASSED])
    return _apply


def test_approved_waiver_turns_the_violation_into_a_waived_warn(factory, payments, apply):
    waiver = factory.waiver(service=payments, version_range=">=4.12.0,<4.13.0")

    waived, untouched = apply()

    assert (waived.outcome, waived.waiver_id) == ("warn", waiver.id)
    assert waived.message == "waived: " + BLOCKED.message and waived.details == BLOCKED.details
    assert untouched == PASSED


@pytest.mark.parametrize("override", [
    {"status": "pending"},
    {"status": "revoked"},
    {"rule": "sast.new_high_max"},
    {"expires_at": TODAY},  # expired at this instant, not swept yet
    {"version_range": ">=4.13.0"},
])
def test_waivers_that_do_not_cover_the_result(factory, payments, apply, override):
    factory.waiver(service=payments, **override)

    assert apply()[0] == BLOCKED


def test_scope_by_service_team_and_missing_version(factory, payments, apply):
    team = factory.team_of(payments)
    factory.waiver(service=factory.service(team))  # another service of the team
    factory.waiver(team=factory.team())  # another team
    ranged = factory.waiver(team=team, version_range=">=1.0")

    assert apply()[0].waiver_id == ranged.id
    assert apply(version=None)[0] == BLOCKED


def test_several_matches_pick_the_one_expiring_last(factory, payments, apply):
    team = factory.team_of(payments)
    factory.waiver(team=team, expires_at=TODAY + timedelta(days=3))
    last = factory.waiver(service=payments, expires_at=TODAY + timedelta(days=9))
    factory.waiver(team=team, expires_at=TODAY + timedelta(days=9))

    assert apply()[0].waiver_id == last.id
