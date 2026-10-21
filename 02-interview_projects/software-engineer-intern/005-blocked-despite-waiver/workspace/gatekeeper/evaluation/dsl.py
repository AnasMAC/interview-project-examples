"""Policy YAML -> ``Policy`` (docs/policy-dsl.md has the reference).

::

    policy: 1                       # DSL version, required; only 1 exists
    rules:                          # non-empty list, evaluated in this order
      - id: <rule id>               # see rules.RULES; each rule at most once
        action: block | warn        # default block
        <param>: <value>            # the rule's own parameters (max / min)
        when:                       # optional
          branches: [<glob>, ...]
          environments: [<name>, ...]

Validation is strict: unknown keys anywhere, wrong YAML types (``max: "0"``,
``max: true``), duplicate mapping keys and duplicate rules are errors. Every
problem is collected and reported at once as ``invalid_policy`` with
``details.errors = [{"path": "rules[2].max", "message": ...}]``.

``sast.max_high`` (the 3.1 name) is still accepted as an alias of
``sast.new_high_max`` and logs ``evaluation.deprecated_rule_alias``.
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from typing import Any

import yaml
from yaml.constructor import ConstructorError

from gatekeeper.core.errors import ValidationFailed
from gatekeeper.core.logging import get_logger
from gatekeeper.evaluation.conditions import Condition, normalize_environment
from gatekeeper.evaluation.rules import REQUIRED, RULES, canonical_rule_id

log = get_logger(__name__)

MAX_SOURCE_BYTES = 64 * 1024
DSL_VERSIONS = (1,)
ACTIONS = ("block", "warn")
_TOP_KEYS = {"policy", "rules"}
_RULE_KEYS = {"id", "action", "when"}
_WHEN_KEYS = {"branches", "environments"}

Errors = list[tuple[str, str]]


@dataclass(frozen=True)
class RuleSpec:
    id: str  # canonical id
    action: str
    params: dict[str, Any]
    when: Condition | None
    declared_as: str  # the id as written in the YAML (differs for an alias)


@dataclass(frozen=True)
class Policy:
    version: int
    rules: tuple[RuleSpec, ...]
    warnings: tuple[str, ...] = ()


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys instead of keeping the last one."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if isinstance(key, Hashable):  # unhashable keys are reported by super()
                if key in seen:
                    raise ConstructorError(
                        "while constructing a mapping", node.start_mark,
                        f"found duplicate key {key!r}", key_node.start_mark,
                    )
                seen.add(key)
        return super().construct_mapping(node, deep=deep)


def invalid_policy(errors: Errors) -> ValidationFailed:
    path, message = errors[0]
    summary = f"{path} {message}" if path else message
    if len(errors) > 1:
        summary += f" (and {len(errors) - 1} more)"
    return ValidationFailed(
        f"policy is invalid: {summary}",
        code="invalid_policy",
        details={"errors": [{"path": p, "message": m} for p, m in errors]},
    )


def _yaml_problem(exc: yaml.YAMLError) -> str:
    problem = getattr(exc, "problem", None) or str(exc)
    mark = getattr(exc, "problem_mark", None)
    return f"{problem} at line {mark.line + 1}, column {mark.column + 1}" if mark else problem


def _unknown_keys(raw: dict[Any, Any], allowed: set[str], path: str, errors: Errors) -> None:
    prefix = f"{path}." if path else ""
    for key in sorted(str(k) for k in raw.keys() - allowed):
        errors.append((f"{prefix}{key}", "unknown key"))


def parse_policy(source: str) -> Policy:
    if len(source.encode()) > MAX_SOURCE_BYTES:
        raise invalid_policy([("", f"policy is larger than {MAX_SOURCE_BYTES} bytes")])
    try:
        document = yaml.load(source, Loader=_StrictLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        raise invalid_policy([("", f"not valid YAML: {_yaml_problem(exc)}")]) from exc
    if not isinstance(document, dict):
        raise invalid_policy([("", "policy must be a YAML mapping with 'policy' and 'rules'")])

    errors: Errors = []
    warnings: list[str] = []
    _unknown_keys(document, _TOP_KEYS, "", errors)
    version = document.get("policy")
    if "policy" not in document:
        errors.append(("policy", "is required (policy: 1)"))
    elif type(version) is not int or version not in DSL_VERSIONS:
        errors.append(("policy", f"unsupported DSL version {version!r}; supported: 1"))

    raw_rules = document.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        errors.append(("rules", "must be a non-empty list of rules"))
        raw_rules = []
    specs: list[RuleSpec] = []
    defined_at: dict[str, str] = {}
    for index, raw in enumerate(raw_rules):
        path = f"rules[{index}]"
        spec = _parse_rule(raw, path, errors, warnings)
        if spec is None:
            continue
        if spec.id in defined_at:
            errors.append((f"{path}.id", f"duplicate rule {spec.id} (also {defined_at[spec.id]})"))
            continue
        defined_at[spec.id] = path
        specs.append(spec)

    if errors:
        raise invalid_policy(errors)
    return Policy(version, tuple(specs), tuple(warnings))


def _parse_rule(raw: Any, path: str, errors: Errors, warnings: list[str]) -> RuleSpec | None:
    if not isinstance(raw, dict):
        errors.append((path, "must be a mapping with an 'id'"))
        return None
    declared = raw.get("id")
    if not isinstance(declared, str) or not declared:
        errors.append((f"{path}.id", "is required"))
        return None
    rule_id = canonical_rule_id(declared)
    rule = RULES.get(rule_id)
    if rule is None:
        errors.append((f"{path}.id", f"unknown rule {declared!r}; known: {', '.join(RULES)}"))
        return None
    if rule_id != declared:
        warnings.append(f"{path}: {declared} is deprecated, use {rule_id}")
        log.warning(
            "evaluation.deprecated_rule_alias", extra={"rule": declared, "replacement": rule_id}
        )

    before = len(errors)
    _unknown_keys(raw, _RULE_KEYS | rule.params.keys(), path, errors)
    action = raw.get("action", "block")
    if not isinstance(action, str) or action not in ACTIONS:
        errors.append((f"{path}.action", "must be block or warn"))
    params: dict[str, Any] = {}
    for name, param in rule.params.items():
        if name not in raw:
            if param.default is REQUIRED:
                errors.append((f"{path}.{name}", "is required"))
            else:
                params[name] = param.default
            continue
        try:
            params[name] = param.parse(raw[name])
        except ValueError as exc:
            errors.append((f"{path}.{name}", str(exc)))
    when = _parse_when(raw["when"], f"{path}.when", errors) if "when" in raw else None
    if len(errors) > before:
        return None
    return RuleSpec(rule_id, action, params, when, declared)


def _parse_when(raw: Any, path: str, errors: Errors) -> Condition | None:
    if not isinstance(raw, dict) or not raw:
        errors.append((path, "must be a mapping with branches and/or environments"))
        return None
    _unknown_keys(raw, _WHEN_KEYS, path, errors)
    branches = _string_list(raw, "branches", path, errors)
    names = _string_list(raw, "environments", path, errors)
    environments: list[str] | None = None
    if names is not None:
        environments = []
        for index, name in enumerate(names):
            canonical = normalize_environment(name)
            if canonical is None:
                errors.append((
                    f"{path}.environments[{index}]",
                    f"unknown environment {name!r}; use production, staging or development",
                ))
            elif canonical not in environments:
                environments.append(canonical)
    return Condition(branches, tuple(environments) if environments is not None else None)


def _string_list(
    raw: dict[str, Any], key: str, path: str, errors: Errors
) -> tuple[str, ...] | None:
    if key not in raw:
        return None
    value = raw[key]
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
        errors.append((f"{path}.{key}", "must be a non-empty list of strings"))
        return None
    return tuple(value)
