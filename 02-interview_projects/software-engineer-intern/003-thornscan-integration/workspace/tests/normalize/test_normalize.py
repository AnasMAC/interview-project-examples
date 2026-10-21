import unittest

from ledger.core.models import Location, Repo, Severity
from ledger.normalize.cwe import parse_cwe
from ledger.normalize.finding import normalize
from ledger.normalize.paths import normalize_path
from ledger.normalize.severity import SEVERITY_TABLE, normalize_severity
from tests.helpers import raw_finding

ROUTE_PLANNER = Repo(3, "route-planner", "routing/route-planner",
                     "https://git.fernwick.example.test/routing/route-planner", "main", 2)


class PathTest(unittest.TestCase):
    def test_paths(self):
        cases = [
            ("src/route_planner/solver.py", "src/route_planner/solver.py"),
            ("./src/route_planner/solver.py", "src/route_planner/solver.py"),
            ("././src//route_planner/./solver.py", "src/route_planner/solver.py"),
            ("src\\route_planner\\solver.py", "src/route_planner/solver.py"),
            ("  src/Route_Planner/Solver.py ", "src/Route_Planner/Solver.py"),
            ("file://src/a%20b.py", "src/a b.py"),
            ("file:///builds/routing/route-planner/src/solver.py", "src/solver.py"),
            ("file:///C:/ci/work/route-planner/src/solver.py", "src/solver.py"),
            ("/builds/routing/route-planner/src/solver.py", "src/solver.py"),
            ("/builds/fleet/route-planner/src/solver.py", "src/solver.py"),
            ("/builds/fleet/planning/route-planner/src/solver.py", "src/solver.py"),
            ("C:\\ci\\work\\route-planner\\src\\solver.py", "src/solver.py"),
            ("c:\\builds\\routing\\route-planner\\src\\solver.py", "src/solver.py"),
            ("/home/ci/work/route-planner/src/solver.py", "src/solver.py"),
            ("/builds/routing/route-planner/tools/route-planner/cli.py", "tools/route-planner/cli.py"),
            ("/opt/scan/route-planner", "/opt/scan/route-planner"),
            ("/usr/lib/python3.11/ssl.py", "/usr/lib/python3.11/ssl.py"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_path(raw, repo=ROUTE_PLANNER), expected)

    def test_without_repo_uses_known_ci_prefixes(self):
        self.assertEqual(normalize_path("/builds/routing/route-planner/src/solver.py"), "src/solver.py")
        self.assertEqual(normalize_path("C:\\ci\\work\\route-planner\\src\\solver.py"), "src/solver.py")
        self.assertEqual(normalize_path("/srv/route-planner/src/solver.py"), "/srv/route-planner/src/solver.py")


class SeverityTest(unittest.TestCase):
    def test_tables(self):
        cases = [
            ("brackish", "error", Severity.HIGH), ("brackish", "warning", Severity.MEDIUM),
            ("thistle", "note", Severity.LOW), ("thistle", "none", Severity.INFO),
            ("kitewatch", "5", Severity.CRITICAL), ("kitewatch", "1", Severity.INFO),
            ("kitewatch", "Critical", Severity.CRITICAL), ("kitewatch", "Informational", Severity.INFO),
            ("depwarden", "MODERATE", Severity.MEDIUM), ("depwarden", "HIGH", Severity.HIGH),
            ("pentest", " Low ", Severity.LOW), ("pentest", "informational", Severity.INFO),
            ("Brackish", "ERROR", Severity.HIGH), ("thornscan", "critical", Severity.CRITICAL),
        ]
        for tool, native, expected in cases:
            with self.subTest(tool=tool, native=native):
                self.assertEqual(normalize_severity(tool, native), expected)
        self.assertEqual(set(SEVERITY_TABLE), {"brackish", "thistle", "kitewatch", "depwarden", "pentest"})

    def test_unknown_label_is_medium_and_logged(self):
        for tool, native in (("brackish", "fatal"), ("kitewatch", "6"), ("thornscan", "P1")):
            with self.subTest(tool=tool, native=native), self.assertLogs("ledger.normalize", "WARNING") as logs:
                self.assertEqual(normalize_severity(tool, native), Severity.MEDIUM)
            self.assertEqual(logs.records[0].getMessage(), "normalize.unknown_severity")
            self.assertEqual((logs.records[0].tool, logs.records[0].label), (tool, native))


class CweTest(unittest.TestCase):
    def test_parse(self):
        for value in ("CWE-89", "cwe_89", "CWE 89", "cwe:89", "CWE-089", "89", " CWE-89: SQL Injection", 89):
            with self.subTest(value=value):
                self.assertEqual(parse_cwe(value), 89)
        for value in (None, "", "CWE-", "SQL injection", "OWASP-A03", 0, -1, "CWE-0", True, "89a"):
            with self.subTest(value=value):
                self.assertIsNone(parse_cwe(value))


class NormalizeTest(unittest.TestCase):
    def test_code_finding(self):
        location = Location.code(".\\src\\solver.py", 8, 2)
        raw = raw_finding(tool="thistle", severity="warning", cwe=None, location=location, extra={"cwe": "CWE-22"})
        finding = normalize(raw, repo=ROUTE_PLANNER)
        self.assertIs(finding.raw, raw)
        self.assertEqual((finding.severity, finding.cwe), (Severity.MEDIUM, 22))
        self.assertEqual(finding.location, Location.code("src/solver.py", 8, 2))

    def test_other_locations_are_kept(self):
        url = Location.endpoint("https://routes.fernwick.example.test/api/v2/plan/./x", "depot")
        package = Location.dependency("Harbor-JSON", "2.3.1")
        for location in (url, package):
            with self.subTest(location=location):
                raw = raw_finding(tool="depwarden", severity="HIGH", location=location, cwe=1395)
                self.assertEqual(normalize(raw, repo=ROUTE_PLANNER).location, location)


if __name__ == "__main__":
    unittest.main()
