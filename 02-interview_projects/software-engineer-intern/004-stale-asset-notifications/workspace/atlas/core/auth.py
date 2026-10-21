"""Per-org API keys and the DRF authentication class.

Keys look like ``atl_DEMO_`` + 32 characters of ``[a-z0-9]``. Only the
SHA-256 of the key is stored, plus its first 16 characters (``prefix``) so a
lookup needs no full-table scan. Keys are random, so an unsalted hash is fine.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import secrets
import string
from datetime import timedelta

from rest_framework import authentication, exceptions

from atlas.core import clock
from atlas.core.models import ApiKey, Org

KEY_PREFIX = "atl_DEMO_"
PREFIX_LENGTH = 16
_ALPHABET = string.ascii_lowercase + string.digits
_LAST_USED_RESOLUTION = timedelta(minutes=1)


@dataclasses.dataclass(frozen=True)
class ApiClient:
    """``request.user`` for API requests; ``request.auth`` is the ApiKey."""

    org: Org
    api_key: ApiKey
    is_authenticated: bool = True
    is_anonymous: bool = False


def generate_key() -> str:
    return KEY_PREFIX + "".join(secrets.choice(_ALPHABET) for _ in range(32))


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_api_key(org: Org, name: str, raw: str | None = None) -> tuple[ApiKey, str]:
    """Create a key; the raw value is returned once and never stored."""
    raw = raw or generate_key()
    key = ApiKey.objects.create(org=org, name=name, prefix=raw[:PREFIX_LENGTH], key_hash=hash_key(raw))
    return key, raw


def authenticate_key(raw: str) -> ApiKey | None:
    if not raw.startswith(KEY_PREFIX) or len(raw) <= PREFIX_LENGTH:
        return None
    digest = hash_key(raw)
    candidates = ApiKey.objects.select_related("org").filter(
        prefix=raw[:PREFIX_LENGTH], revoked_at__isnull=True
    )
    for key in candidates:
        if hmac.compare_digest(key.key_hash, digest):
            return key
    return None


def revoke_api_key(key: ApiKey) -> None:
    if key.revoked_at is None:
        key.revoked_at = clock.now()
        key.save(update_fields=["revoked_at"])


class ApiKeyAuthentication(authentication.BaseAuthentication):
    """``Authorization: Bearer atl_DEMO_...``; no header means anonymous (401 later)."""

    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("latin-1")
        if header == "":
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            raise exceptions.AuthenticationFailed("Expected 'Authorization: Bearer <api key>'.")
        key = authenticate_key(parts[1])
        if key is None:
            raise exceptions.AuthenticationFailed("Invalid or revoked API key.")
        now = clock.now()
        if key.last_used_at is None or now - key.last_used_at >= _LAST_USED_RESOLUTION:
            ApiKey.objects.filter(pk=key.pk).update(last_used_at=now)
            key.last_used_at = now
        return ApiClient(org=key.org, api_key=key), key

    def authenticate_header(self, request) -> str:
        return self.keyword
