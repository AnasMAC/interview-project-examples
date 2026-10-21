import pytest
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from atlas.core import auth
from atlas.core.models import ApiKey
from tests.factories import make_api_key

pytestmark = pytest.mark.django_db


def _authenticate(header: str | None):
    extra = {} if header is None else {"HTTP_AUTHORIZATION": header}
    request = Request(APIRequestFactory().get("/api/v1/assets/", **extra))
    return auth.ApiKeyAuthentication().authenticate(request)


def test_valid_key_authenticates_as_its_org(org):
    key, raw = make_api_key(org)
    assert raw.startswith("atl_DEMO_") and len(raw) == 41
    assert key.key_hash != raw and raw not in str(key)
    client, auth_key = _authenticate(f"Bearer {raw}")
    assert client.org == org and client.is_authenticated
    assert auth_key == key


def test_no_header_is_anonymous():
    assert _authenticate(None) is None


@pytest.mark.parametrize("header", ["Token abc", "Bearer", "Bearer a b", "Basic dXNlcjpwYXNz"])
def test_malformed_header_is_rejected(header):
    with pytest.raises(exceptions.AuthenticationFailed):
        _authenticate(header)


def test_wrong_key_with_same_prefix_is_rejected(org):
    _, raw = make_api_key(org)
    forged = raw[: auth.PREFIX_LENGTH] + "x" * (len(raw) - auth.PREFIX_LENGTH)
    assert auth.authenticate_key(forged) is None


def test_revoked_key_is_rejected(org):
    key, raw = make_api_key(org)
    auth.revoke_api_key(key)
    with pytest.raises(exceptions.AuthenticationFailed):
        _authenticate(f"Bearer {raw}")


def test_two_keys_sharing_a_prefix_resolve_to_their_own_org(org, other_org):
    shared = "atl_DEMO_aaaaaaa"
    mine, raw_mine = make_api_key(org, raw=shared + "1" * 25)
    _, raw_other = make_api_key(other_org, raw=shared + "2" * 25)
    assert auth.authenticate_key(raw_mine) == mine
    assert auth.authenticate_key(raw_other).org == other_org


def test_last_used_at_is_written_at_most_once_a_minute(org, frozen_clock):
    key, raw = make_api_key(org)
    _authenticate(f"Bearer {raw}")
    first = ApiKey.objects.get(pk=key.pk).last_used_at
    frozen_clock.advance(seconds=30)
    _authenticate(f"Bearer {raw}")
    assert ApiKey.objects.get(pk=key.pk).last_used_at == first
    frozen_clock.advance(seconds=30)
    _authenticate(f"Bearer {raw}")
    assert ApiKey.objects.get(pk=key.pk).last_used_at == frozen_clock.now()
