"""Rule semantics, one table per rule; boundaries are the interesting rows."""

from __future__ import annotations

import pytest

from gatekeeper.evaluation import rules


def _deps(*vulns: tuple[str, str, str]) -> dict:
    """(package, advisory id, severity) triples, one package per triple, version 1.0.0."""
    return {"packages": [
        {"name": name, "version": "1.0.0", "ecosystem": "pypi",
         "vulnerabilities": [{"id": vid, "severity": sev}]}
        for name, vid, sev in vulns
    ]}


@pytest.mark.parametrize(
    ("limit", "severities", "ok"),
    [
        ("high", [], True),
        ("high", ["low", "medium"], True),
        ("high", ["high"], True),  # inclusive: the max itself is allowed
        ("high", ["critical"], False),
        ("medium", ["high"], False),
        ("none", ["none"], True),
        ("none", ["low"], False),
        ("critical", ["critical", "critical"], True),
    ],
)
def test_dependency_max_severity_is_inclusive(limit, severities, ok):
    data = _deps(*[(f"pkg{i}", f"MBSA-{i}", s) for i, s in enumerate(severities)])

    assert rules.check_dependencies({"max": limit}, data).ok is ok


def test_dependency_violation_lists_worst_first_with_architecture_message():
    data = _deps(("pdfmint", "MBSA-2025-0310", "high"), ("ledgerkit", "MBSA-2026-0141", "critical"),
                 ("yamlette", "MBSA-2026-0007", "low"))
    data["packages"][1]["version"] = "2.4.1"

    verdict = rules.check_dependencies({"max": "medium"}, data)

    assert verdict.message == "ledgerkit 2.4.1: MBSA-2026-0141 is critical (max medium) and 1 more"
    assert verdict.details == {
        "violations": [
            {"package": "ledgerkit", "id": "MBSA-2026-0141", "severity": "critical"},
            {"package": "pdfmint", "id": "MBSA-2025-0310", "severity": "high"},
        ],
        "count": 2, "max": "medium",
    }


def test_dependency_details_are_capped_but_count_is_exact():
    data = _deps(*[(f"pkg{i}", f"MBSA-{i}", "critical") for i in range(60)])

    verdict = rules.check_dependencies({"max": "high"}, data)

    assert len(verdict.details["violations"]) == rules.MAX_LISTED_VIOLATIONS
    assert verdict.details["count"] == 60


def test_package_without_vulnerabilities_key_passes():
    data = {"packages": [{"name": "flaskwork", "version": "3.0.3", "ecosystem": "pypi"}]}

    assert rules.check_dependencies({"max": "none"}, data).ok


@pytest.mark.parametrize(
    ("limit", "count", "findings", "ok", "message"),
    [
        (0, 0, 0, True, "0 secret findings (max 0)"),
        (0, 1, 1, False, "1 secret finding (max 0)"),
        (2, 2, 2, True, "2 secret findings (max 2)"),
        (2, 3, 0, False, "3 secret findings (max 2)"),  # legacy runner: count only
    ],
)
def test_secrets_allowed_counts_inclusively(limit, count, findings, ok, message):
    data = {"count": count,
            "findings": [{"detector": "generic-api-key", "path": "app.env", "line": n}
                         for n in range(findings)]}

    verdict = rules.check_secrets({"max": limit}, data)

    assert (verdict.ok, verdict.message) == (ok, message)
    assert verdict.details == {"count": count, "max": limit}


@pytest.mark.parametrize(
    ("limit", "new", "total_high", "ok", "new_high"),
    [
        (0, {"critical": 0, "high": 0, "medium": 9, "low": 9}, 40, True, 0),
        (0, {"critical": 0, "high": 1, "medium": 0, "low": 0}, 1, False, 1),
        (0, {"critical": 1, "high": 0, "medium": 0, "low": 0}, 0, False, 1),
        (2, {"critical": 1, "high": 1, "medium": 0, "low": 0}, 9, True, 2),
        (2, {"critical": 1, "high": 2, "medium": 0, "low": 0}, 9, False, 3),
    ],
)
def test_sast_counts_new_high_and_critical_only(limit, new, total_high, ok, new_high):
    data = {"new": new, "total": {"critical": 0, "high": total_high, "medium": 0, "low": 0}}

    verdict = rules.check_sast({"max": limit}, data)

    assert verdict.ok is ok
    assert verdict.details == {"new_high": new_high, "max": limit}


def test_sast_message_matches_the_documented_reason():
    data = {"new": {"critical": 0, "high": 1, "medium": 2, "low": 0}, "total": None}

    assert rules.check_sast({"max": 0}, data).message == "1 new high SAST finding (max 0)"


@pytest.mark.parametrize(
    ("minimum", "passed", "failed", "skipped", "ok", "rate"),
    [
        (0.95, 19, 1, 0, True, 0.95),  # exactly at the minimum passes
        (0.95, 189, 11, 0, False, 0.945),
        (0.95, 19, 1, 500, True, 0.95),  # skipped tests do not count
        (0.95, 412, 0, 6, True, 1.0),
        (1.0, 999, 1, 0, False, 0.999),
        (0.95, 0, 0, 12, False, None),  # nothing ran: violated
        (0.0, 0, 0, 0, True, None),
        (0.0, 0, 5, 0, True, 0.0),
    ],
)
def test_tests_min_pass_rate(minimum, passed, failed, skipped, ok, rate):
    data = {"passed": passed, "failed": failed, "skipped": skipped}

    verdict = rules.check_tests({"min": minimum}, data)

    assert verdict.ok is ok
    assert verdict.details == {"passed": passed, "failed": failed, "skipped": skipped,
                               "rate": rate, "min": minimum}


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"passed": 189, "failed": 11, "skipped": 0}, "pass rate 94.5% (min 95%)"),
        ({"passed": 0, "failed": 0, "skipped": 3}, "no tests ran (min 95%)"),
    ],
)
def test_tests_messages(data, message):
    assert rules.check_tests({"min": 0.95}, data).message == message


@pytest.mark.parametrize(
    ("signed", "verified", "key_id", "ok", "message"),
    [
        (True, True, "mossbank-release-2026", True, "signed and verified (mossbank-release-2026)"),
        (True, False, "mossbank-release-2026", False,
         "signature by mossbank-release-2026 is not verified"),
        (True, False, None, False, "signature by an unknown key is not verified"),
        (False, False, None, False, "release is not signed"),
        (False, True, None, False, "release is not signed"),
    ],
)
def test_signing_required_needs_signed_and_verified(signed, verified, key_id, ok, message):
    verdict = rules.check_signing({}, {"signed": signed, "verified": verified, "key_id": key_id})

    assert (verdict.ok, verdict.message) == (ok, message)


def test_registry_maps_each_rule_to_its_evidence_kind_and_alias():
    assert {r.id: r.evidence for r in rules.RULES.values()} == {
        "dependency.max_severity": "dependencies", "secrets.allowed": "secrets",
        "sast.new_high_max": "sast", "tests.min_pass_rate": "tests", "signing.required": "signing",
    }
    assert rules.canonical_rule_id("sast.max_high") == "sast.new_high_max"
    assert rules.canonical_rule_id("secrets.allowed") == "secrets.allowed"
