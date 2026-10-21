import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from atlas.core import clock
from tests import factories


@pytest.fixture(autouse=True)
def frozen_clock():
    """Every test runs at TODAY (factories.py); frozen_clock.advance(hours=1) moves it."""
    clock.freeze(factories.TODAY)
    yield clock
    clock.unfreeze()


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()  # throttle counters
    yield
    cache.clear()


@pytest.fixture
def org(db):
    return factories.make_org("harborview-bank")


@pytest.fixture
def other_org(db):
    return factories.make_org("quillstone-media")


def _client_for(org) -> APIClient:
    _, raw = factories.make_api_key(org)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    return client


@pytest.fixture
def api_client(org) -> APIClient:
    return _client_for(org)


@pytest.fixture
def other_api_client(other_org) -> APIClient:
    return _client_for(other_org)


@pytest.fixture
def dashboard_user(org):
    return factories.make_user("rafael", orgs=[org])


@pytest.fixture
def dashboard_client(client, dashboard_user):
    client.force_login(dashboard_user)
    return client
