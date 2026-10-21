import unittest

from ledger.core.models import Location, Repo
from ledger.dedupe.fingerprint import FINGERPRINT_VERSION, fingerprint
from ledger.dedupe.issue_key import issue_key
from ledger.normalize.finding import normalize
from tests.helpers import raw_finding

REPO = Repo(1, "checkout-api", "payments/checkout-api", "https://git.fernwick.example.test/payments/checkout-api",
            "main", 1)


def norm(**fields):
    fields.setdefault("severity", "high")  # a label every tool accepts
    return normalize(raw_finding(**fields), repo=REPO)


class FingerprintTest(unittest.TestCase):
    def test_pinned_value(self):
        # Changing this value orphans every stored finding: bump FINGERPRINT_VERSION and migrate instead.
        self.assertEqual(FINGERPRINT_VERSION, 1)
        self.assertEqual(fingerprint(norm()), "8e4e01432c5deec260a0c4769bbc16603fbf10e44b155f1a9107c84662dba607")

    def test_stable_across_spellings_of_the_path(self):
        paths = ["src/payments/refunds.py", "./src/payments/refunds.py", "src\\payments\\refunds.py",
                 "/builds/payments/checkout-api/src/payments/refunds.py",
                 "file:///builds/x/checkout-api/src/payments/refunds.py"]
        values = {fingerprint(norm(location=Location.code(path, 42))) for path in paths}
        self.assertEqual(len(values), 1)

    def test_fields_that_count(self):
        base = fingerprint(norm())
        for change in ({"tool": "thistle"}, {"rule_id": "BRK-SQLI-002"},
                       {"location": Location.code("src/payments/refunds.py", 43, 9)},
                       {"location": Location.code("src/payments/Refunds.py", 42, 9)}):
            with self.subTest(change=change):
                self.assertNotEqual(fingerprint(norm(**change)), base)

    def test_fields_that_do_not_count(self):
        base = fingerprint(norm())
        for change in ({"message": "Reworded"}, {"severity": "warning"}, {"evidence": "cursor.execute(q)"},
                       {"cwe": 564}, {"tool_fingerprint": "abc"},
                       {"location": Location.code("src/payments/refunds.py", 42, 30)}):
            with self.subTest(change=change):
                self.assertEqual(fingerprint(norm(**change)), base)

    def test_endpoint_and_package_locations(self):
        url = "https://checkout.fernwick.example.test/api/refunds"
        by_param = {fingerprint(norm(tool="kitewatch", location=Location.endpoint(url, p))) for p in ("id", "q", None)}
        self.assertEqual(len(by_param), 3)
        packages = [Location.dependency("harbor-json", version) for version in ("2.3.1", "2.4.0")]
        versions = {fingerprint(norm(tool="depwarden", location=location)) for location in packages}
        self.assertEqual(len(versions), 1)  # upgrading to a still-vulnerable version keeps the finding


class IssueKeyTest(unittest.TestCase):
    def test_sast_key(self):
        self.assertEqual(issue_key(norm()), "src/payments/refunds.py:42:CWE-89")
        windows = Location.code("C:\\ci\\work\\checkout-api\\src\\payments\\refunds.py", 42, 1)
        thistle = norm(tool="thistle", rule_id="py.sqli", location=windows)
        self.assertEqual(issue_key(thistle), issue_key(norm()))
        self.assertEqual(issue_key(norm(cwe=None, extra={"cwe": "CWE-89"})), "src/payments/refunds.py:42:CWE-89")

    def test_no_key(self):
        cases = {
            "no cwe": norm(cwe=None),
            "no line": norm(location=Location.code("src/payments/refunds.py")),
            "dast": norm(tool="kitewatch", location=Location.endpoint("https://checkout.fernwick.example.test/", "q")),
            "pentest on code": norm(tool="pentest"),
            "dependency": norm(tool="depwarden", location=Location.dependency("harbor-json", "2.3.1")),
        }
        for name, finding in cases.items():
            with self.subTest(name):
                self.assertIsNone(issue_key(finding))


if __name__ == "__main__":
    unittest.main()
