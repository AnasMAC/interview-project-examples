"""SARIF 2.1.0 logs from our SAST tools, Brackish and Thistle.

The tool name comes from ``runs[].tool.driver.name`` (lowercased); one file
holds one tool. The two tools differ in small ways:

* Brackish writes repo-relative URIs with ``uriBaseId: "%SRCROOT%"`` (no base
  URI given) and 1-based ``startColumn``, as the spec says.
* Thistle runs inside the CI workspace and writes absolute URIs, either
  directly (``file:///builds/<group>/<repo>/...``) or relative to an
  ``originalUriBaseIds`` entry, which is resolved here. The path is kept as
  written otherwise; ``normalize`` strips the workspace. Thistle before 5.0
  writes 0-based ``startColumn`` (vendor ticket TH-2210); Ledger stores
  1-based columns.

Results with ``kind`` ``pass``/``notApplicable`` and results suppressed in
source (an accepted ``suppressions`` entry, e.g. ``# brackish: ignore``) are
not findings. The native severity is the result ``level``, falling back to
the rule's ``defaultConfiguration.level`` and then to SARIF's ``warning``.
"""

from __future__ import annotations

import re
from typing import Any

from ledger.core import log
from ledger.core.errors import ParseError
from ledger.core.models import Location, ParsedReport, RawFinding
from ledger.parsers.common import cwe_from, head, items, load_json, obj, optional_int, text_or_none

# Tool -> first major version that writes 1-based columns.
ZERO_BASED_COLUMNS_BEFORE = {"thistle": 5}

_SCHEMA = re.compile(r'"\$schema"\s*:\s*"[^"]*sarif', re.IGNORECASE)
_VERSION = re.compile(r'"version"\s*:\s*"2\.1\.0"')
_PLACEHOLDER = re.compile(r"\{(\d+)\}")
_NOT_FINDINGS = {"pass", "notApplicable"}

_log = log.get_logger("parsers.sarif")


def _array(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


class SarifParser:
    format = "sarif"
    extensions = (".sarif", ".json")

    def sniff(self, data: bytes, filename: str | None) -> bool:
        text = head(data)
        if not text.startswith("{"):
            return False
        return bool(_SCHEMA.search(text)) or (bool(_VERSION.search(text)) and '"runs"' in text)

    def parse(self, data: bytes, *, source: str) -> ParsedReport:
        document = load_json(data, source=source)
        if not isinstance(document, dict) or not isinstance(document.get("runs"), list):
            raise ParseError(f"{source}: not a SARIF log (no runs array)", source=source)
        tool: str | None = None
        version: str | None = None
        findings: list[RawFinding] = []
        for index, run in enumerate(document["runs"]):
            driver = obj(obj(obj(run).get("tool")).get("driver"))
            name = (text_or_none(driver.get("name")) or "").lower()
            if not name:
                raise ParseError(f"{source}: runs[{index}] has no tool.driver.name", source=source)
            if tool is not None and name != tool:
                raise ParseError(f"{source}: runs from two tools ({tool}, {name}); upload one file per tool",
                                 source=source)
            tool = name
            version = text_or_none(driver.get("semanticVersion") or driver.get("version")) or version
            run_parser = _Run(tool, version, run, driver, source)
            results = items(run.get("results"), f"runs[{index}].results", source=source)
            findings.extend(finding for finding in map(run_parser.finding, results) if finding is not None)
        if tool is None:
            raise ParseError(f"{source}: SARIF log has no runs", source=source)
        return ParsedReport(format=self.format, tool=tool, findings=tuple(findings), tool_version=version)


class _Run:
    """Per-run state: the rule table, URI bases and the column convention of this tool version."""

    def __init__(self, tool: str, version: str | None, run: dict[str, Any], driver: dict[str, Any],
                 source: str) -> None:
        self.tool = tool
        self.source = source
        self.rules = [obj(rule) for rule in _array(driver.get("rules"))]
        self.rules_by_id = {str(rule.get("id")): rule for rule in self.rules if rule.get("id")}
        self.bases = obj(run.get("originalUriBaseIds"))
        self.column_shift = column_shift(tool, version)

    def finding(self, result: Any) -> RawFinding | None:
        result = obj(result)
        if result.get("kind") in _NOT_FINDINGS or _suppressed_in_source(result):
            return None
        rule = self._rule(result)
        rule_id = text_or_none(result.get("ruleId")) or text_or_none(rule.get("id"))
        if rule_id is None:
            raise ParseError(f"{self.source}: result without ruleId", source=self.source)
        physical = obj(obj((_array(result.get("locations")) or [{}])[0]).get("physicalLocation"))
        uri = self._uri(obj(physical.get("artifactLocation")))
        if uri is None:
            _log.warning("parsers.sarif.no_location", extra={"source": self.source, "rule": rule_id})
            return None
        region = obj(physical.get("region"))
        line = optional_int(region.get("startLine"), "startLine", source=self.source)
        column = optional_int(region.get("startColumn"), "startColumn", source=self.source)
        if column is not None:
            column += self.column_shift
        level = result.get("level") or obj(rule.get("defaultConfiguration")).get("level") or "warning"
        rule_props = obj(rule.get("properties"))
        extra = {
            "rule_name": text_or_none(rule.get("name")),
            "help_uri": text_or_none(rule.get("helpUri")),
            "end_line": text_or_none(region.get("endLine")),
            "security_severity": text_or_none(rule_props.get("security-severity")),
        }
        return RawFinding(
            tool=self.tool,
            rule_id=rule_id,
            severity=str(level),
            location=Location.code(uri, line, column),
            message=self._message(result, rule) or rule_id,
            evidence=text_or_none(obj(region.get("snippet")).get("text")),
            cwe=_cwe(rule_props, obj(result.get("properties"))),
            tool_fingerprint=_fingerprint(result),
            extra={key: value for key, value in extra.items() if value is not None},
        )

    def _rule(self, result: dict[str, Any]) -> dict[str, Any]:
        reference = obj(result.get("rule"))
        rule_id = result.get("ruleId") or reference.get("id")
        if rule_id is not None and str(rule_id) in self.rules_by_id:
            return self.rules_by_id[str(rule_id)]
        index = result.get("ruleIndex", reference.get("index"))
        if isinstance(index, int) and 0 <= index < len(self.rules):
            return self.rules[index]
        return {}

    def _uri(self, artifact: dict[str, Any]) -> str | None:
        uri = text_or_none(artifact.get("uri"))
        base = text_or_none(obj(self.bases.get(artifact.get("uriBaseId"))).get("uri"))
        if uri is not None and base and "://" not in uri and not uri.startswith("/"):
            uri = base.rstrip("/") + "/" + uri
        return uri

    def _message(self, result: dict[str, Any], rule: dict[str, Any]) -> str | None:
        message = obj(result.get("message"))
        text = text_or_none(message.get("text"))
        if text is None and message.get("id"):
            text = text_or_none(obj(obj(rule.get("messageStrings")).get(message["id"])).get("text"))
        if text is None:
            return text_or_none(obj(rule.get("shortDescription")).get("text"))
        arguments = [str(argument) for argument in _array(message.get("arguments"))]

        def fill(match: re.Match[str]) -> str:
            position = int(match.group(1))
            return arguments[position] if position < len(arguments) else match.group(0)

        return _PLACEHOLDER.sub(fill, text)


def column_shift(tool: str, version: str | None) -> int:
    """1 when this tool version writes 0-based columns, else 0."""
    first_one_based = ZERO_BASED_COLUMNS_BEFORE.get(tool)
    if first_one_based is None:
        return 0
    major = (version or "").split(".")[0]
    return 1 if not major.isdigit() or int(major) < first_one_based else 0


def _suppressed_in_source(result: dict[str, Any]) -> bool:
    return any(obj(s).get("status", "accepted") == "accepted" for s in _array(result.get("suppressions")))


def _cwe(rule_props: dict[str, Any], result_props: dict[str, Any]) -> int | None:
    # Thistle states it as a property, Brackish as a GitHub-style tag ("external/cwe/cwe-89").
    for value in (result_props.get("cwe"), rule_props.get("cwe")):
        if (cwe := cwe_from(value)) is not None:
            return cwe
    for tag in _array(rule_props.get("tags")):
        if isinstance(tag, str) and "cwe" in tag.lower() and (cwe := cwe_from(tag)) is not None:
            return cwe
    return None


def _fingerprint(result: dict[str, Any]) -> str | None:
    # Stable `fingerprints` beat `partialFingerprints`; within one, the alphabetically first key.
    for field in ("fingerprints", "partialFingerprints"):
        values = obj(result.get(field))
        if values:
            key = sorted(values)[0]
            return f"{key}={values[key]}"
    return None


PARSER = SarifParser()
