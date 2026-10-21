"""Cross-tool issue key: Brackish and Thistle reporting the same weakness on the same line.

ADR 0002 keyed on path and line; since 2.3 the CWE is part of the key, because
two different weaknesses on one line (an injection and a hard-coded secret)
were merged into a single finding.
"""

from __future__ import annotations

from ledger.core.models import LocationKind
from ledger.normalize.finding import NormalizedFinding

SAST_TOOLS = frozenset({"brackish", "thistle"})


def issue_key(finding: NormalizedFinding) -> str | None:
    """``"<path>:<line>:CWE-<n>"`` for SAST code findings with a line and a CWE, else None."""
    location = finding.location
    if finding.raw.tool not in SAST_TOOLS or location.kind != LocationKind.CODE:
        return None
    if not location.path or location.line is None or finding.cwe is None:
        return None
    return f"{location.path}:{location.line}:CWE-{finding.cwe}"
