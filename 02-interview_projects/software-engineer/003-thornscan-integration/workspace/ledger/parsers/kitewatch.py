"""Kitewatch DAST reports (JSON), schema v2 and v3.

v2 (Kitewatch 2.x)::

    {"kitewatch": "2.9.3", "site": "https://...", "alerts": [
        {"pluginId": "KW-SQLI-001", "alert": "...", "risk": 5, "cweid": "89",
         "instances": [{"uri": "...", "method": "POST", "param": "order_id", "evidence": "..."}]}]}

One alert per check, one finding per instance. ``risk`` is an integer from 1
(informational) to 5 (critical); ``cweid`` is ``-1`` or ``0`` when unknown.

v3 (Kitewatch 3.x, handled since Ledger 2.2)::

    {"schema": "https://schemas.kitewatch.example.test/report/v3.json",
     "scanner": {"name": "Kitewatch", "version": "3.2.1"},
     "findings": [{"rule": "KW-SQLI-001", "title": "...", "severity": "Critical", "cwe": "CWE-89",
                   "request": {"method": "POST", "url": "...", "parameter": "order_id"},
                   "evidence": "...", "fingerprint": "kw3:..."}]}

One finding per request; severity is a word. Rule ids did not change
between the versions. The native label is kept as reported (``"5"`` or
``"Critical"``); ``normalize.severity`` knows both scales.
"""

from __future__ import annotations

import re
from typing import Any

from ledger.core.errors import ParseError
from ledger.core.models import Location, ParsedReport, RawFinding
from ledger.parsers.common import cwe_from, head, items, load_json, obj, text_or_none

TOOL = "kitewatch"
V2_RISKS = range(1, 6)

_SNIFF_V2 = re.compile(r'"kitewatch"\s*:\s*"')
_SNIFF_V3 = re.compile(r'"schema"\s*:\s*"[^"]*kitewatch[^"]*/v3\b', re.IGNORECASE)


class KitewatchParser:
    format = "kitewatch"
    extensions = (".json",)

    def sniff(self, data: bytes, filename: str | None) -> bool:
        text = head(data)
        return text.startswith("{") and bool(_SNIFF_V2.search(text) or _SNIFF_V3.search(text))

    def parse(self, data: bytes, *, source: str) -> ParsedReport:
        document = load_json(data, source=source)
        if not isinstance(document, dict):
            raise ParseError(f"{source}: Kitewatch report must be a JSON object", source=source)
        if "kitewatch" in document:
            version, findings = text_or_none(document["kitewatch"]), _parse_v2(document, source)
        elif "findings" in document:
            version, findings = text_or_none(obj(document.get("scanner")).get("version")), _parse_v3(document, source)
        else:
            raise ParseError(f"{source}: neither a Kitewatch v2 nor v3 report", source=source)
        return ParsedReport(format=self.format, tool=TOOL, findings=tuple(findings), tool_version=version)


def _parse_v2(document: dict[str, Any], source: str) -> list[RawFinding]:
    findings = []
    for number, alert in enumerate(items(document.get("alerts"), "alerts", source=source)):
        alert = obj(alert)
        rule_id = text_or_none(alert.get("pluginId"))
        risk = alert.get("risk")
        if isinstance(risk, str) and risk.strip().isdigit():
            risk = int(risk)
        if rule_id is None or isinstance(risk, bool) or risk not in V2_RISKS:
            raise ParseError(f"{source}: alerts[{number}] needs a pluginId and a risk from 1 to 5", source=source,
                             alert=number)
        for instance in items(alert.get("instances"), "instances", source=source):
            instance = obj(instance)
            url = text_or_none(instance.get("uri"))
            if url is None:
                raise ParseError(f"{source}: alerts[{number}] has an instance without uri", source=source,
                                 alert=number)
            findings.append(RawFinding(
                tool=TOOL,
                rule_id=rule_id,
                severity=str(risk),
                location=Location.endpoint(url, text_or_none(instance.get("param"))),
                message=text_or_none(alert.get("alert")) or rule_id,
                evidence=text_or_none(instance.get("evidence")),
                cwe=cwe_from(alert.get("cweid")),
                extra=_extra(method=instance.get("method"), confidence=alert.get("confidence"),
                             solution=alert.get("solution")),
            ))
    return findings


def _parse_v3(document: dict[str, Any], source: str) -> list[RawFinding]:
    findings = []
    for number, item in enumerate(items(document.get("findings"), "findings", source=source)):
        item = obj(item)
        request = obj(item.get("request"))
        rule_id, severity = text_or_none(item.get("rule")), text_or_none(item.get("severity"))
        url = text_or_none(request.get("url"))
        if rule_id is None or severity is None or url is None:
            raise ParseError(f"{source}: findings[{number}] needs rule, severity and request.url", source=source,
                             finding=number)
        findings.append(RawFinding(
            tool=TOOL,
            rule_id=rule_id,
            severity=severity,
            location=Location.endpoint(url, text_or_none(request.get("parameter"))),
            message=text_or_none(item.get("title")) or rule_id,
            evidence=text_or_none(item.get("evidence")),
            cwe=cwe_from(item.get("cwe")),
            tool_fingerprint=text_or_none(item.get("fingerprint")),
            extra=_extra(method=request.get("method"), confidence=item.get("confidence"),
                         solution=item.get("remediation")),
        ))
    return findings


def _extra(**values: Any) -> dict[str, str]:
    return {key: text for key, value in values.items() if (text := text_or_none(value)) is not None}


PARSER = KitewatchParser()
