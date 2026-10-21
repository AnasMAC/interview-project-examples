"""Role ranks, tenant scoping and the cross-tenant 404 rule.

The unit tests below cover the rank helpers; the request-level behaviour
(``tenant_scope``, ``require_role`` on views, tenant filters on rows) needs the
database and belongs with the tests that cover the routes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import permissions


def test_role_ranks_are_ordered() -> None:
    assert permissions.rank("requester") < permissions.rank("agent")
    assert permissions.rank("agent") < permissions.rank("admin")


def test_has_role_uses_the_minimum_rank() -> None:
    agent = SimpleNamespace(role="agent")
    admin = SimpleNamespace(role="admin")
    assert permissions.has_role(agent, "requester")
    assert permissions.has_role(agent, "agent")
    assert not permissions.has_role(agent, "admin")
    assert permissions.has_role(admin, "agent")
    assert not permissions.has_role(SimpleNamespace(role="requester"), "agent")


def test_unknown_roles_raise() -> None:
    with pytest.raises(ValueError):
        permissions.rank("owner")
    assert not permissions.has_role(SimpleNamespace(role="owner"), "requester")


def test_tenant_matches_without_an_identity_is_false() -> None:
    assert permissions.tenant_matches(1) is False
    assert permissions.tenant_matches(None) is False
