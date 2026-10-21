from __future__ import annotations

import logging

import pytest

from gatekeeper.core.errors import ValidationFailed
from gatekeeper.evaluation.conditions import Condition
from gatekeeper.evaluation.dsl import MAX_SOURCE_BYTES, RuleSpec, parse_policy
from tests.factories import DEFAULT_POLICY


def _errors(source: str) -> list[dict[str, str]]:
    with pytest.raises(ValidationFailed) as excinfo:
        parse_policy(source)
    assert excinfo.value.code == "invalid_policy"
    return excinfo.value.details["errors"]


def _rule(body: str) -> str:
    return f"policy: 1\nrules:\n  - {body}\n"


def test_default_policy_parses_in_order_with_defaults_and_conditions():
    policy = parse_policy(DEFAULT_POLICY)

    assert policy.version == 1 and policy.warnings == ()
    assert [r.id for r in policy.rules] == [
        "dependency.max_severity", "secrets.allowed", "sast.new_high_max",
        "tests.min_pass_rate", "signing.required",
    ]
    assert policy.rules[0] == RuleSpec(
        "dependency.max_severity", "block", {"max": "high"}, None, "dependency.max_severity"
    )
    assert policy.rules[2].action == "warn"
    assert policy.rules[3].params == {"min": 0.95}
    assert policy.rules[4].when == Condition(None, ("production",))


def test_defaults_action_block_and_zero_maximums():
    policy = parse_policy("policy: 1\nrules:\n  - id: secrets.allowed\n  - id: sast.new_high_max\n")

    assert [(r.action, r.params) for r in policy.rules] == [("block", {"max": 0})] * 2


def test_deprecated_sast_max_high_is_an_alias_with_a_warning(caplog):
    caplog.set_level(logging.WARNING, logger="gatekeeper.evaluation.dsl")

    policy = parse_policy(_rule("{id: sast.max_high, max: 2, action: warn}"))

    assert policy.rules[0].id == "sast.new_high_max"
    assert policy.rules[0].declared_as == "sast.max_high"
    assert policy.rules[0].params == {"max": 2}
    assert policy.warnings == ("rules[0]: sast.max_high is deprecated, use sast.new_high_max",)
    [record] = [r for r in caplog.records if r.msg == "evaluation.deprecated_rule_alias"]
    assert (record.rule, record.replacement) == ("sast.max_high", "sast.new_high_max")


def test_when_branches_environments_and_aliases():
    policy = parse_policy(_rule(
        "{id: signing.required, when: {branches: [main, 'release/*'], "
        "environments: [prod, Staging, production]}}"
    ))

    assert policy.rules[0].when == Condition(("main", "release/*"), ("production", "staging"))


def test_severity_and_ratio_values_are_normalized():
    policy = parse_policy(
        "policy: 1\nrules:\n  - {id: dependency.max_severity, max: ' Critical '}\n"
        "  - {id: tests.min_pass_rate, min: 1}\n"
    )

    assert policy.rules[0].params == {"max": "critical"}
    assert policy.rules[1].params == {"min": 1.0}


@pytest.mark.parametrize(
    ("source", "path", "message"),
    [
        ("rules: [\n", "", "not valid YAML"),
        ("- policy: 1\n", "", "must be a YAML mapping"),
        ("", "", "must be a YAML mapping"),
        ("rules:\n  - {id: secrets.allowed}\n", "policy", "is required"),
        ("policy: 2\nrules:\n  - {id: secrets.allowed}\n", "policy", "unsupported DSL version 2"),
        ("policy: '1'\nrules:\n  - {id: secrets.allowed}\n", "policy", "unsupported"),
        ("policy: true\nrules:\n  - {id: secrets.allowed}\n", "policy", "unsupported"),
        ("policy: 1\nrules:\n  - {id: secrets.allowed}\nmode: warn\n", "mode", "unknown key"),
        ("policy: 1\n", "rules", "non-empty list"),
        ("policy: 1\nrules: []\n", "rules", "non-empty list"),
        ("policy: 1\nrules: {id: secrets.allowed}\n", "rules", "non-empty list"),
        ("policy: 1\nrules:\n  - secrets.allowed\n", "rules[0]", "must be a mapping"),
        (_rule("{max: 0}"), "rules[0].id", "is required"),
        (_rule("{id: licence.allowed}"), "rules[0].id", "unknown rule 'licence.allowed'"),
        (_rule("{id: secrets.allowed, maximum: 0}"), "rules[0].maximum", "unknown key"),
        (_rule("{id: secrets.allowed, min: 0}"), "rules[0].min", "unknown key"),
        (_rule("{id: signing.required, max: 0}"), "rules[0].max", "unknown key"),
        (_rule("{id: secrets.allowed, action: deny}"), "rules[0].action", "block or warn"),
        (_rule("{id: secrets.allowed, action: [warn]}"), "rules[0].action", "block or warn"),
        (_rule("{id: secrets.allowed, max: '0'}"), "rules[0].max", "whole number"),
        (_rule("{id: secrets.allowed, max: true}"), "rules[0].max", "whole number"),
        (_rule("{id: secrets.allowed, max: -1}"), "rules[0].max", "whole number"),
        (_rule("{id: sast.new_high_max, max: 0.5}"), "rules[0].max", "whole number"),
        (_rule("{id: dependency.max_severity}"), "rules[0].max", "is required"),
        (_rule("{id: dependency.max_severity, max: severe}"), "rules[0].max", "one of none"),
        (_rule("{id: dependency.max_severity, max: 3}"), "rules[0].max", "one of none"),
        (_rule("{id: tests.min_pass_rate}"), "rules[0].min", "is required"),
        (_rule("{id: tests.min_pass_rate, min: 95}"), "rules[0].min", "between 0 and 1"),
        (_rule("{id: tests.min_pass_rate, min: -0.1}"), "rules[0].min", "between 0 and 1"),
        (_rule("{id: tests.min_pass_rate, min: '95%'}"), "rules[0].min", "between 0 and 1"),
        (_rule("{id: signing.required, when: {}}"), "rules[0].when", "must be a mapping"),
        (_rule("{id: signing.required, when: [main]}"), "rules[0].when", "must be a mapping"),
        (_rule("{id: signing.required, when: {branch: [main]}}"), "rules[0].when.branch",
         "unknown key"),
        (_rule("{id: signing.required, when: {branches: main}}"), "rules[0].when.branches",
         "non-empty list of strings"),
        (_rule("{id: signing.required, when: {branches: []}}"), "rules[0].when.branches",
         "non-empty list of strings"),
        (_rule("{id: signing.required, when: {branches: [main, 4.12]}}"),
         "rules[0].when.branches", "non-empty list of strings"),
        (_rule("{id: signing.required, when: {environments: []}}"),
         "rules[0].when.environments", "non-empty list of strings"),
        (_rule("{id: signing.required, when: {environments: [production, qa]}}"),
         "rules[0].when.environments[1]", "unknown environment 'qa'"),
        ("policy: 1\nrules:\n  - {id: secrets.allowed}\n  - {id: secrets.allowed, max: 1}\n",
         "rules[1].id", "duplicate rule secrets.allowed (also rules[0])"),
        ("policy: 1\nrules:\n  - {id: sast.new_high_max}\n  - {id: sast.max_high}\n",
         "rules[1].id", "duplicate rule sast.new_high_max"),
        ("policy: 1\nrules:\n  - id: secrets.allowed\n    max: 0\n    max: 3\n", "",
         "found duplicate key 'max' at line 5"),
    ],
)
def test_invalid_policies_name_the_offending_path(source, path, message):
    errors = _errors(source)

    assert errors[0]["path"] == path
    assert message in errors[0]["message"]


def test_every_problem_is_reported_at_once():
    source = (
        "policy: 3\nowner: payments\nrules:\n"
        "  - {id: secrets.allowed, max: x, action: deny}\n"
        "  - {id: tests.min_pass_rate, min: 2}\n"
    )

    with pytest.raises(ValidationFailed) as excinfo:
        parse_policy(source)

    assert [e["path"] for e in excinfo.value.details["errors"]] == [
        "owner", "policy", "rules[0].action", "rules[0].max", "rules[1].min",
    ]
    assert excinfo.value.message.startswith("policy is invalid: owner unknown key (and 4 more)")


def test_oversized_source_is_rejected_before_parsing():
    source = "policy: 1\nrules:\n  - {id: secrets.allowed}\n" + "#" * MAX_SOURCE_BYTES

    assert "larger than" in _errors(source)[0]["message"]


def test_yaml_tags_that_build_python_objects_are_refused():
    errors = _errors("policy: !!python/object/apply:os.system ['true']\nrules: []\n")

    assert "not valid YAML" in errors[0]["message"]
