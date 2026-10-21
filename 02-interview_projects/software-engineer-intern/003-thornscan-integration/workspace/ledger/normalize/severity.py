"""Tool-native severity labels -> Ledger severities.

Every tool also accepts our own five words, so a parser that already maps
to them (or a pentest report written by hand) needs no table entry. Labels
are compared lowercased and stripped. Changing a mapping changes SLAs of
new and reopened findings only; existing rows keep their severity.
"""

from __future__ import annotations

from ledger.core import log
from ledger.core.models import Severity

_SARIF_LEVELS = {"error": Severity.HIGH, "warning": Severity.MEDIUM, "note": Severity.LOW, "none": Severity.INFO}

SEVERITY_TABLE: dict[str, dict[str, Severity]] = {
    # SARIF `level`: neither SAST tool can say "critical" on its own.
    "brackish": dict(_SARIF_LEVELS),
    "thistle": dict(_SARIF_LEVELS),
    # v2 reports numbers (5 is worst), v3 words; both are still in use (CHANGELOG 2.2).
    "kitewatch": {
        "5": Severity.CRITICAL, "4": Severity.HIGH, "3": Severity.MEDIUM, "2": Severity.LOW, "1": Severity.INFO,
        "informational": Severity.INFO,
    },
    # NVD labels, plus "moderate" from GitHub advisories and "unknown" for a CVE not scored yet.
    "depwarden": {"moderate": Severity.MEDIUM, "unknown": Severity.MEDIUM},
    "pentest": {"informational": Severity.INFO, "none": Severity.INFO},
}

_COMMON = {severity.value: severity for severity in Severity}
_log = log.get_logger("normalize.severity")


def normalize_severity(tool: str, native: str) -> Severity:
    """Map ``native`` for ``tool``; an unknown label becomes MEDIUM and is logged."""
    label = str(native).strip().lower()
    table = SEVERITY_TABLE.get(tool.lower(), {})
    severity = table.get(label) or _COMMON.get(label)
    if severity is None:
        _log.warning("normalize.unknown_severity", extra={"tool": tool, "label": native})
        return Severity.MEDIUM
    return severity
