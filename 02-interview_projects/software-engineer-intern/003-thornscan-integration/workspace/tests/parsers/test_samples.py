"""The checked-in sample reports parse, match the demo manifest and keep the facts `make demo` relies on."""

from __future__ import annotations

import json
import re
import unittest
from collections import defaultdict

from ledger.core.config import ROOT
from ledger.core.errors import UnknownFormat
from ledger.parsers import registry

SAMPLES = ROOT / "samples"


def _load_manifest() -> list[dict]:
    return json.loads((SAMPLES / "manifest.json").read_text(encoding="utf-8"))["runs"]


class SamplesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runs = _load_manifest()
        cls.reports = [registry.parse_report((SAMPLES / run["file"]).read_bytes(), source=run["file"])
                       for run in cls.runs]

    def test_manifest_entries(self) -> None:
        for run, report in zip(self.runs, self.reports):
            with self.subTest(file=run["file"]):
                self.assertIn(run["repo"], ("checkout-api", "route-planner"))
                self.assertRegex(run["commit"], r"^[0-9a-f]{40}$")
                self.assertEqual(report.tool, run["tool"])
                self.assertTrue(run["file"].startswith(f"{run['tool']}/{run['repo']}/"))
                self.assertTrue(report.findings)

    def test_every_sample_report_is_in_the_manifest(self) -> None:
        listed = {run["file"] for run in self.runs}
        on_disk = {path.relative_to(SAMPLES).as_posix() for tool in ("brackish", "thistle", "kitewatch",
                   "depwarden", "pentest") for path in (SAMPLES / tool).rglob("*") if path.is_file()}
        self.assertEqual(on_disk, listed)

    def test_every_tool_and_both_kitewatch_versions(self) -> None:
        self.assertEqual({r.tool for r in self.reports}, {"brackish", "thistle", "kitewatch", "depwarden", "pentest"})
        kitewatch = {r.tool_version.split(".")[0] for r in self.reports if r.tool == "kitewatch"}
        self.assertEqual(kitewatch, {"2", "3"})

    def test_brackish_and_thistle_overlap_on_path_line_and_cwe(self) -> None:
        seen = defaultdict(set)
        for run, report in zip(self.runs, self.reports):
            for finding in report.findings:
                if report.tool in ("brackish", "thistle"):
                    path = finding.location.path.replace("\\", "/")
                    path = re.sub(r"^file://(/[A-Za-z]:)?/builds/[^/]+/[^/]+/", "", path)
                    seen[(run["repo"], run["commit"], path, finding.location.line, finding.cwe)].add(report.tool)
        both = sorted((key[0], key[2], key[3]) for key, tools in seen.items() if len(tools) == 2)
        self.assertIn(("checkout-api", "src/payments/refunds.py", 42), both)
        self.assertIn(("route-planner", "planner/cache.py", 55), both)
        self.assertGreaterEqual(len(both), 7)

    def test_thornscan_attachment_has_no_parser_yet(self) -> None:
        self.assertTrue((SAMPLES / "thornscan" / "FORMAT.md").is_file())
        for path in (SAMPLES / "thornscan").rglob("*.jsonl"):
            with self.subTest(file=path.name):
                lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(lines[0]["record"], "header")
                if lines[-1]["record"] == "summary":  # no summary when the job timed out (REQ-0061)
                    self.assertEqual(lines[-1]["issues"], sum(line["record"] == "issue" for line in lines))
                with self.assertRaises(UnknownFormat):
                    registry.detect(path.read_bytes(), path.name)


if __name__ == "__main__":
    unittest.main()
