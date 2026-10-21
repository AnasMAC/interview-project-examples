from __future__ import annotations

import unittest

from ledger.core.errors import ParseError
from ledger.core.models import Location
from ledger.parsers.depwarden import PARSER

VULN = """<{p}vulnerability id="DWA-2026-0142" severity="HIGH" cvss="7.5">
        <{p}cwe>CWE-611</{p}cwe><{p}title>iterparse resolves external entities</{p}title>
        <{p}affected>&gt;=4.0.0,&lt;4.2.3</{p}affected><{p}fixed>4.2.3</{p}fixed>
      </{p}vulnerability>"""

V4 = f"""<?xml version="1.0" encoding="UTF-8"?>
<report xmlns="urn:depwarden:report:4">
  <scanner name="Depwarden" version="4.3.0"/>
  <project name="checkout-api" ecosystem="pypi" manifest="requirements.lock"/>
  <dependencies>
    <dependency name="lxml-lite" version="4.2.1" direct="false">
      <path>checkout-api &gt; invoicegen 2.0.4 &gt; lxml-lite 4.2.1</path>
      {VULN.format(p="")}
      <vulnerability id="DWA-2026-0150" severity="LOW"><title>Slow on deep trees</title></vulnerability>
    </dependency>
    <dependency name="flask-lite" version="3.0.2"/>
  </dependencies>
</report>"""

V3 = f"""<?xml version="1.0"?>
<dw:report xmlns:dw="http://schemas.depwarden.example.test/report/3" tool-version="3.9.1">
  <dw:project name="route-planner" ecosystem="pypi"/>
  <dw:dependencies>
    <dw:dependency name="geojsonkit" requested="&gt;=0.8,&lt;1.0">{VULN.format(p="dw:")}</dw:dependency>
  </dw:dependencies>
</dw:report>"""


def parse(text: str):
    return PARSER.parse(text.encode(), source="depwarden.xml")


class DepwardenTest(unittest.TestCase):
    def test_v4_default_namespace(self) -> None:
        report = parse(V4)
        self.assertEqual((report.tool, report.tool_version), ("depwarden", "4.3.0"))
        first, second = report.findings
        self.assertEqual(first.location, Location.dependency("lxml-lite", "4.2.1"))
        self.assertEqual((first.rule_id, first.severity, first.cwe), ("DWA-2026-0142", "HIGH", 611))
        self.assertEqual(first.message, "iterparse resolves external entities")
        self.assertEqual(first.evidence, "checkout-api > invoicegen 2.0.4 > lxml-lite 4.2.1")
        self.assertEqual(first.extra["affected"], ">=4.0.0,<4.2.3")
        self.assertEqual(first.extra["fixed_in"], "4.2.3")
        self.assertEqual(first.extra["ecosystem"], "pypi")  # inherited from <project>
        self.assertNotIn("version_is_range", first.extra)
        self.assertEqual((second.rule_id, second.cwe), ("DWA-2026-0150", None))

    def test_v3_prefixed_namespace_and_requested_range(self) -> None:
        report = parse(V3)
        self.assertEqual(report.tool_version, "3.9.1")
        (finding,) = report.findings
        self.assertEqual(finding.location, Location.dependency("geojsonkit", ">=0.8,<1.0"))
        self.assertEqual(finding.extra["version_is_range"], "true")

    def test_resolved_version_wins_over_the_range(self) -> None:
        text = V3.replace('requested="', 'version="0.9.1" requested="')
        (finding,) = parse(text).findings
        self.assertEqual(finding.location.version, "0.9.1")
        self.assertNotIn("version_is_range", finding.extra)

    def test_no_namespace_at_all(self) -> None:
        text = V4.replace(' xmlns="urn:depwarden:report:4"', "")
        self.assertEqual(len(parse(text).findings), 2)

    def test_doctype_is_refused(self) -> None:
        bomb = '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><report>&a;</report>'
        with self.assertRaisesRegex(ParseError, "DOCTYPE"):
            parse(bomb)

    def test_errors(self) -> None:
        with self.assertRaises(ParseError) as ctx:
            parse('<report xmlns="urn:depwarden:report:4">\n<dependency name="x">\n</report>')
        self.assertEqual(ctx.exception.details["line"], 3)
        for text in ('<summary xmlns="urn:depwarden:report:4"/>',
                     '<report><dependency version="1.0"/></report>',
                     '<report><dependency name="x"><vulnerability id="DWA-1"/></dependency></report>'):
            with self.subTest(text=text), self.assertRaises(ParseError):
                parse(text)

    def test_sniff(self) -> None:
        self.assertTrue(PARSER.sniff(V4.encode(), None))
        self.assertTrue(PARSER.sniff(V3.encode(), None))
        self.assertFalse(PARSER.sniff(b'<?xml version="1.0"?><testsuites name="depwarden"/>', None))


if __name__ == "__main__":
    unittest.main()
