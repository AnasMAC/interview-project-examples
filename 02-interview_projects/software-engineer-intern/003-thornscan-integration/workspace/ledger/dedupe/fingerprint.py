"""Per-tool finding fingerprints: same tool, rule and place -> same finding across runs.

Version 1 hashes the normalized location, not the message (tools reword
messages between releases) and not the column or the dependency version
(a partial upgrade must not restart the SLA clock). Line numbers are in, so
code that moves above a finding makes it "fixed" plus "new"; see
``FINGERPRINT_VERSION`` before changing any field: every stored fingerprint
would have to be recomputed.
"""

from __future__ import annotations

import hashlib

from ledger.core.models import LocationKind
from ledger.normalize.finding import NormalizedFinding

FINGERPRINT_VERSION = 1


def fingerprint(finding: NormalizedFinding) -> str:
    """sha256 hex over version, tool, rule and the location fields."""
    location = finding.location
    if location.kind == LocationKind.CODE:
        place = [location.path, location.line]
    elif location.kind == LocationKind.URL:
        place = [location.url, location.parameter]
    else:
        place = [location.package]
    fields = [f"v{FINGERPRINT_VERSION}", finding.raw.tool, finding.raw.rule_id, location.kind.value, *place]
    text = "\x1f".join("" if value is None else str(value) for value in fields)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
