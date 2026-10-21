"""Asset identity: the ``key`` that makes (org, kind, key) unique.

Importers already normalize what they emit; the merge step runs every value
through ``identity_key`` again so that a sloppy source (or the API) can never
create a second asset for the same thing.
"""

from __future__ import annotations

import re

from atlas.assets.models import Asset
from atlas.core.normalize import NormalizationError, normalize_cidr, normalize_hostname, normalize_ip

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def identity_key(kind: str, value: str) -> str:
    """Canonical key for an asset of ``kind``; raises ``NormalizationError``."""
    if kind in (Asset.Kind.DOMAIN, Asset.Kind.HOST):
        return normalize_hostname(value)
    if kind == Asset.Kind.IP:
        return normalize_ip(value)
    if kind == Asset.Kind.NETWORK:
        return normalize_cidr(value)
    if kind == Asset.Kind.CERTIFICATE:
        # Fingerprints are often printed as "AB:CD:...".
        fingerprint = value.strip().lower().replace(":", "")
        if _SHA256.match(fingerprint) is None:
            raise NormalizationError(f"certificate key must be a SHA-256 hex digest: {value!r}")
        return fingerprint
    if kind == Asset.Kind.CLOUD_RESOURCE:
        parts = value.strip().lower().split(":")
        if len(parts) != 3 or parts[0] != "nimbus" or not all(parts):
            raise NormalizationError(f"cloud resource key must be nimbus:<account>:<resource>: {value!r}")
        return ":".join(parts)
    raise NormalizationError(f"unknown asset kind {kind!r}")


def identity_kinds(kind: str) -> tuple[str, ...]:
    """Kinds that share one identity space with ``kind``.

    A hostname is one asset whether a source calls it a ``domain`` (the zone
    apex) or a ``host`` (a CT SAN, a scan target): the merge and the API look
    a hostname up under both kinds, domain first.
    """
    if kind in (Asset.Kind.DOMAIN, Asset.Kind.HOST):
        return (Asset.Kind.DOMAIN, Asset.Kind.HOST)
    return (kind,)


def default_attributes(kind: str, key: str) -> dict:
    """Attributes every asset of ``kind`` carries even when a source says nothing."""
    if kind in (Asset.Kind.IP, Asset.Kind.NETWORK):
        return {"version": 6 if ":" in key else 4}
    return {}
