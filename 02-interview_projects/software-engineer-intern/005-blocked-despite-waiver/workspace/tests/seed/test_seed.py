from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from gatekeeper.core.auth import authenticate
from gatekeeper.core.tables import (
    audit_events,
    callback_outbox,
    evaluations,
    evidence,
    policies,
    services,
    teams,
    waivers,
)
from gatekeeper.evaluation.dsl import parse_policy
from gatekeeper.seed.data import ANCHOR
from gatekeeper.seed.generate import SeedError, generate

CONTRACT_KEYS = {
    "payments-api-ci": "gk_demo_709fff51dcac6661eec4c8205afc7b4c",
    "settlement-sg-ci": "gk_demo_f2dcce435ff54bf9768e66ee0a4a03b6",
    "kyc-platform-ci": "gk_demo_afae81c508208e40106f6e5dca45973e",
    "security-review": "gk_demo_3619a3a300d893fb961215d0ba824465",
    "grace.adeyemi": "gk_demo_58f64bee26b143d5e6de4249553d4844",
}


def _count(conn, table, *where):
    return conn.execute(select(func.count()).select_from(table).where(*where)).scalar()


def test_seed_matches_the_contract(conn):
    summary = generate(conn)
    assert summary["teams"] == 12 and summary["services"] == 40
    assert 7600 <= summary["evaluations"] <= 8400
    assert _count(conn, evidence) == 5 * summary["evaluations"]
    assert set(summary["waivers"]) == {"pending", "approved", "rejected", "revoked", "expired"}
    assert set(summary["callback_outbox"]) == {"pending", "delivered", "dead"}
    assert summary["audit_events"] > summary["evaluations"]

    sg = conn.execute(select(teams).where(teams.c.id == 4)).one()
    assert (sg.slug, sg.timezone) == ("settlement-sg", "Asia/Singapore")
    payments = conn.execute(select(teams).where(teams.c.slug == "payments-api")).one()
    assert payments.callback_secret == "DEMO-whsec-payments-api-16b97cb36173"
    assert conn.execute(select(services.c.slug).where(services.c.team_id == payments.id)
                        .order_by(services.c.id)).scalars().all() == [
        "payments-api", "payments-webhooks", "refunds-worker"]
    for name, key in CONTRACT_KEYS.items():
        assert authenticate(conn, key).name == name
    for source in conn.execute(select(policies.c.source)).scalars():
        parse_policy(source)
    assert _count(conn, waivers, waivers.c.team_id == 4, waivers.c.status == "approved",
                  waivers.c.expires_at < ANCHOR + timedelta(hours=72)) == 1
    assert _count(conn, audit_events, audit_events.c.action == "waiver.applied") > 20
    with pytest.raises(SeedError):
        generate(conn)


def test_seed_is_deterministic_and_scales(conn):
    def snapshot():
        rows = select(evaluations.c.commit_sha, evaluations.c.decision).order_by(evaluations.c.id)
        return conn.execute(rows).all()

    generate(conn, seed=3, scale=0.05)
    first = snapshot()
    generate(conn, seed=3, scale=0.05, reset=True)
    assert snapshot() == first
    assert 380 <= len(first) <= 420
    generate(conn, seed=4, scale=0.05, reset=True)
    assert snapshot() != first
    assert _count(conn, callback_outbox) > 0
