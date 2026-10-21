"""Depwarden dependency reports (XML).

Depwarden 4 writes a default namespace ``urn:depwarden:report:4``; Depwarden 3
used ``http://schemas.depwarden.example.test/report/3`` with a ``dw:`` prefix.
Elements are matched by local name, so both read the same::

    <report xmlns="urn:depwarden:report:4">
      <scanner name="Depwarden" version="4.3.0"/>
      <project name="checkout-api" ecosystem="pypi" manifest="requirements.lock"/>
      <dependency name="fastjwt" version="1.8.0" direct="true">
        <path>checkout-api &gt; fastjwt 1.8.0</path>
        <vulnerability id="DWA-2025-0917" severity="CRITICAL">
          <cwe>CWE-347</cwe> <title>...</title>
          <affected>&lt;1.9.0</affected> <fixed>1.9.0</fixed>
        </vulnerability>
      </dependency>
    </report>

A project without a lock file has no resolved ``version``, only the
``requested`` range from the manifest (``>=0.8,<1.0``, ``~=2.1``). The range is
then kept as the location version and marked ``extra["version_is_range"]``;
a resolved version always wins. ``affected`` is the advisory's vulnerable
range and is informational only.

Reports with a DOCTYPE are refused: Depwarden never writes one, and entity
declarations are how XML bombs arrive.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ledger.core.errors import ParseError
from ledger.core.models import Location, ParsedReport, RawFinding
from ledger.parsers.common import cwe_from, head, text_or_none

TOOL = "depwarden"

_SNIFF = re.compile(r"<(?:[\w.-]+:)?report\b[^>]*depwarden", re.IGNORECASE | re.DOTALL)
_DOCTYPE = re.compile(rb"<!DOCTYPE", re.IGNORECASE)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _local(child.tag) == name]


def _child_text(element: ET.Element, name: str) -> str | None:
    found = _children(element, name)
    return text_or_none(found[0].text) if found else None


def _line(error: ET.ParseError) -> int | None:
    position = getattr(error, "position", None)
    return position[0] if position else None


class DepwardenParser:
    format = "depwarden"
    extensions = (".xml",)

    def sniff(self, data: bytes, filename: str | None) -> bool:
        text = head(data)
        return text.startswith("<") and bool(_SNIFF.search(text))

    def parse(self, data: bytes, *, source: str) -> ParsedReport:
        if _DOCTYPE.search(data):
            raise ParseError(f"{source}: DOCTYPE declarations are not accepted", source=source)
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise ParseError(f"{source}: invalid XML ({exc})", source=source, line=_line(exc)) from exc
        if _local(root.tag) != "report":
            raise ParseError(f"{source}: expected a Depwarden <report>, got <{_local(root.tag)}>", source=source)
        scanner = _children(root, "scanner")
        version = text_or_none(scanner[0].get("version")) if scanner else text_or_none(root.get("tool-version"))
        project = _children(root, "project")
        default_ecosystem = text_or_none(project[0].get("ecosystem")) if project else None
        findings: list[RawFinding] = []
        for dependency in root.iter():
            if _local(dependency.tag) == "dependency":
                findings.extend(self._dependency(dependency, default_ecosystem, source))
        return ParsedReport(format=self.format, tool=TOOL, findings=tuple(findings), tool_version=version)

    def _dependency(self, dependency: ET.Element, default_ecosystem: str | None, source: str) -> list[RawFinding]:
        package = text_or_none(dependency.get("name"))
        resolved = text_or_none(dependency.get("version"))
        requested = text_or_none(dependency.get("requested"))
        if package is None:
            raise ParseError(f"{source}: <dependency> without name", source=source)
        extra = {"ecosystem": text_or_none(dependency.get("ecosystem")) or default_ecosystem,
                 "direct": text_or_none(dependency.get("direct")),
                 "scope": text_or_none(dependency.get("scope"))}
        if resolved is None and requested is not None:
            extra["version_is_range"] = "true"
        location = Location.dependency(package, resolved or requested)
        evidence = _child_text(dependency, "path")
        findings = []
        for vulnerability in _children(dependency, "vulnerability"):
            advisory = text_or_none(vulnerability.get("id"))
            severity = text_or_none(vulnerability.get("severity"))
            if advisory is None or severity is None:
                raise ParseError(f"{source}: vulnerability of {package} needs id and severity", source=source,
                                 package=package)
            details = {**extra, "affected": _child_text(vulnerability, "affected"),
                       "fixed_in": _child_text(vulnerability, "fixed"), "cvss": text_or_none(vulnerability.get("cvss"))}
            findings.append(RawFinding(
                tool=TOOL,
                rule_id=advisory,
                severity=severity,
                location=location,
                message=_child_text(vulnerability, "title") or f"{advisory} in {package}",
                evidence=evidence,
                cwe=cwe_from(_child_text(vulnerability, "cwe")),
                extra={key: value for key, value in details.items() if value is not None},
            ))
        return findings


PARSER = DepwardenParser()
