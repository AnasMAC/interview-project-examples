from __future__ import annotations

import json
import unittest

from ledger.core.errors import ParseError, UnknownFormat
from ledger.core.models import ParsedReport
from ledger.parsers import registry

SARIF = json.dumps({
    "$schema": "https://schemas.fernwick.example.test/mirror/sarif-2.1.0.json",
    "version": "2.1.0",
    "runs": [{"tool": {"driver": {"name": "Brackish"}}, "results": []}],
}).encode()
KITEWATCH = json.dumps({"kitewatch": "2.9.3", "alerts": []}).encode()
DEPWARDEN = b'<?xml version="1.0"?>\n<report xmlns="urn:depwarden:report:4"><scanner name="Depwarden"/></report>'
PENTEST = b"ID;Title;Severity;Asset\r\n"


class _Claims:
    """A parser that claims every input; stands in for a future format that overlaps the built-ins."""

    def __init__(self, fmt: str, extensions: tuple[str, ...] = ()) -> None:
        self.format = fmt
        self.extensions = extensions

    def sniff(self, data: bytes, filename: str | None) -> bool:
        return True

    def parse(self, data: bytes, *, source: str) -> ParsedReport:
        return ParsedReport(format=self.format, tool=self.format)


class DetectTest(unittest.TestCase):
    def setUp(self) -> None:
        registry.formats()  # builtins first, so cleanup restores exactly them
        self.addCleanup(self._restore, dict(registry._parsers))

    @staticmethod
    def _restore(saved: dict) -> None:
        registry._parsers.clear()
        registry._parsers.update(saved)

    def test_builtin_formats_in_sniffing_order(self) -> None:
        self.assertEqual(registry.formats(), ["sarif", "kitewatch", "depwarden", "pentest_csv"])

    def test_content_decides_not_the_file_name(self) -> None:
        cases = {SARIF: "sarif", KITEWATCH: "kitewatch", DEPWARDEN: "depwarden", PENTEST: "pentest_csv"}
        for data, fmt in cases.items():
            with self.subTest(fmt=fmt):
                self.assertEqual(registry.detect(data, "report.txt").format, fmt)
                self.assertEqual(registry.detect(b"\xef\xbb\xbf  \n" + data).format, fmt)

    def test_sarif_without_schema_is_still_sarif(self) -> None:
        data = b'{"version": "2.1.0", "runs": []}'
        self.assertEqual(registry.detect(data).format, "sarif")

    def test_unknown_and_empty_content(self) -> None:
        for data in (b"", b"  \n", b'{"issues": []}', b"<html></html>", b"just text"):
            with self.subTest(data=data), self.assertRaises(UnknownFormat):
                registry.detect(data, "x.json")

    def test_thornscan_jsonl_is_not_claimed_yet(self) -> None:
        data = b'{"record": "header", "tool": "thornscan", "version": "1.4.2"}\n{"record": "summary"}\n'
        with self.assertRaises(UnknownFormat) as ctx:
            registry.parse_report(data, source="thornscan.jsonl")
        self.assertEqual(ctx.exception.status, 415)
        self.assertEqual(ctx.exception.details["source"], "thornscan.jsonl")

    def test_file_name_breaks_a_tie(self) -> None:
        registry.register(_Claims("fake_xml", (".xml",)))
        self.assertEqual(registry.detect(DEPWARDEN, "deps.xml").format, "depwarden")  # both claim, first wins
        self.assertEqual(registry.detect(KITEWATCH, "scan.json").format, "kitewatch")
        self.assertEqual(registry.detect(b"anything", "a.xml").format, "fake_xml")

    def test_suffix_match_beats_registration_order(self) -> None:
        registry.register(_Claims("fake_sarif", (".sarif",)))
        self.assertEqual(registry.detect(KITEWATCH, "odd.sarif").format, "fake_sarif")
        self.assertEqual(registry.detect(KITEWATCH, "odd.json").format, "kitewatch")

    def test_register_rejects_a_taken_format(self) -> None:
        with self.assertRaises(ValueError):
            registry.register(_Claims("sarif"))
        parser = _Claims("extra")
        self.assertIs(registry.register(parser), parser)
        self.assertIs(registry.register(parser), parser)  # idempotent for the same object

    def test_parser_bugs_on_odd_input_become_parse_errors(self) -> None:
        class _Broken(_Claims):
            def parse(self, data: bytes, *, source: str) -> ParsedReport:
                return {}["runs"]

        registry.register(_Broken("broken"))
        with self.assertRaises(ParseError) as ctx, self.assertLogs("ledger.parsers.registry", "WARNING"):
            registry.parse_report(b"{}", source="odd.json", fmt="broken")
        self.assertEqual((ctx.exception.status, ctx.exception.details), (422, {"source": "odd.json"}))

    def test_get_parser(self) -> None:
        self.assertEqual(registry.get_parser("depwarden").format, "depwarden")
        with self.assertRaises(UnknownFormat):
            registry.get_parser("thornscan")


class ParseReportTest(unittest.TestCase):
    def test_explicit_format_skips_detection(self) -> None:
        with self.assertRaises(ParseError) as ctx:
            registry.parse_report(KITEWATCH, source="k.json", fmt="sarif")
        self.assertEqual(ctx.exception.details["source"], "k.json")

    def test_parses_detected_format(self) -> None:
        report = registry.parse_report(SARIF, source="brackish.sarif")
        self.assertEqual((report.format, report.tool, report.findings), ("sarif", "brackish", ()))


if __name__ == "__main__":
    unittest.main()
