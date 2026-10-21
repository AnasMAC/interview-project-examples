"""The canonical rules: their parameters, the evidence they read and the check.

Each check gets the rule's parsed parameters and the normalized evidence of
its kind (docs/architecture.md, "Evidence") and returns a ``Verdict``. The
evaluator turns a failed verdict into the rule's ``action``; a missing
evidence kind never reaches the check.

Thresholds, exactly:

* ``dependency.max_severity`` ``max``: the highest *allowed* severity
  (inclusive). ``max: high`` passes a high and blocks a critical.
* ``secrets.allowed`` ``max`` (default 0): allowed findings (inclusive),
  counted with ``count``, which can exceed ``len(findings)``.
* ``sast.new_high_max`` ``max`` (default 0): allowed *new* high + critical
  findings (inclusive). ``total`` and medium/low findings are ignored.
* ``tests.min_pass_rate`` ``min`` in 0..1: ``passed / (passed + failed)``,
  skipped excluded, must be ``>= min``. No executed test fails the rule
  unless ``min`` is 0.
* ``signing.required``: the artifact is signed *and* the signature verified.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from gatekeeper.core.contracts import SEVERITIES, severity_rank

REQUIRED = object()
MAX_LISTED_VIOLATIONS = 50
# Deprecated spellings -> canonical id. Waivers are stored under the canonical id.
ALIASES = {"sast.max_high": "sast.new_high_max"}


@dataclass(frozen=True)
class Verdict:
    ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Param:
    parse: Callable[[Any], Any]  # raises ValueError with a message for the policy author
    default: Any = REQUIRED


@dataclass(frozen=True)
class Rule:
    id: str
    evidence: str
    params: dict[str, Param]
    check: Callable[[dict[str, Any], dict[str, Any]], Verdict]


def canonical_rule_id(rule_id: str) -> str:
    return ALIASES.get(rule_id, rule_id)


def _severity(value: Any) -> str:
    if not isinstance(value, str) or value.strip().lower() not in SEVERITIES:
        raise ValueError(f"must be one of {', '.join(SEVERITIES)}")
    return value.strip().lower()


def _count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("must be a whole number >= 0")
    return value


def _ratio(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= 1:
        raise ValueError("must be a number between 0 and 1 (0.95 means 95%)")
    return float(value)


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _percent(ratio: float) -> str:
    return f"{ratio * 100:g}%"


def check_dependencies(params: dict[str, Any], data: dict[str, Any]) -> Verdict:
    limit = params["max"]
    found = [
        (pkg, vuln)
        for pkg in data["packages"]
        for vuln in pkg.get("vulnerabilities", [])
        if severity_rank(vuln["severity"]) > severity_rank(limit)
    ]
    if not found:
        return Verdict(True, f"no vulnerabilities above {limit}", {"max": limit})
    found.sort(key=lambda pair: -severity_rank(pair[1]["severity"]))  # worst first, stable
    pkg, vuln = found[0]
    message = f"{pkg['name']} {pkg['version']}: {vuln['id']} is {vuln['severity']} (max {limit})"
    if len(found) > 1:
        message += f" and {len(found) - 1} more"
    violations = [
        {"package": p["name"], "id": v["id"], "severity": v["severity"]}
        for p, v in found[:MAX_LISTED_VIOLATIONS]
    ]
    return Verdict(False, message, {"violations": violations, "count": len(found), "max": limit})


def check_secrets(params: dict[str, Any], data: dict[str, Any]) -> Verdict:
    count, limit = data["count"], params["max"]
    return Verdict(
        count <= limit,
        f"{_plural(count, 'secret finding')} (max {limit})",
        {"count": count, "max": limit},
    )


def check_sast(params: dict[str, Any], data: dict[str, Any]) -> Verdict:
    new_high = data["new"]["high"] + data["new"]["critical"]
    limit = params["max"]
    return Verdict(
        new_high <= limit,
        f"{_plural(new_high, 'new high SAST finding')} (max {limit})",
        {"new_high": new_high, "max": limit},
    )


def check_tests(params: dict[str, Any], data: dict[str, Any]) -> Verdict:
    minimum = params["min"]
    passed, failed, skipped = data["passed"], data["failed"], data["skipped"]
    details: dict[str, Any] = {
        "passed": passed, "failed": failed, "skipped": skipped, "rate": None, "min": minimum,
    }
    executed = passed + failed
    if executed == 0:
        return Verdict(minimum == 0, f"no tests ran (min {_percent(minimum)})", details)
    rate = passed / executed
    details["rate"] = round(rate, 4)
    return Verdict(
        rate >= minimum, f"pass rate {rate:.1%} (min {_percent(minimum)})", details
    )


def check_signing(params: dict[str, Any], data: dict[str, Any]) -> Verdict:
    signed, verified, key_id = data["signed"], data["verified"], data.get("key_id")
    details = {"signed": signed, "verified": verified, "key_id": key_id}
    if not signed:
        return Verdict(False, "release is not signed", details)
    if not verified:
        return Verdict(False, f"signature by {key_id or 'an unknown key'} is not verified", details)
    return Verdict(True, f"signed and verified ({key_id or 'unknown key'})", details)


RULES: dict[str, Rule] = {
    rule.id: rule
    for rule in (
        Rule("dependency.max_severity", "dependencies", {"max": Param(_severity)},
             check_dependencies),
        Rule("secrets.allowed", "secrets", {"max": Param(_count, 0)}, check_secrets),
        Rule("sast.new_high_max", "sast", {"max": Param(_count, 0)}, check_sast),
        Rule("tests.min_pass_rate", "tests", {"min": Param(_ratio)}, check_tests),
        Rule("signing.required", "signing", {}, check_signing),
    )
}
