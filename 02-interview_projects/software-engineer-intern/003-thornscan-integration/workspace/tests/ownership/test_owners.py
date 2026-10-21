import unittest

from ledger.core.config import ROOT
from ledger.core.errors import ParseError
from ledger.core.models import Location
from ledger.ownership.owners import OwnerRule, load_owners, parse_owners
from ledger.ownership.teams import owners_path, resolve_team_id
from tests.helpers import LedgerTestCase, make_repo, make_team

SAMPLE = """\
# Payments owns the repository
*                       @fernwick/payments

/src/checkout/auth/     @fernwick/identity   # vendored from auth-gateway
*.sql                   @fernwick/data
docs/                   @docs
/deploy/**/*.yaml       @fernwick/platform
/src/checkout/auth/refund_tokens.py  @fernwick/payments
/README.md              @fernwick/docs
"""


class ParseOwnersTest(unittest.TestCase):
    def test_rules_keep_slug_and_line(self):
        owners = parse_owners(SAMPLE)
        self.assertEqual(owners.rules[0], OwnerRule("*", "payments", 2))
        self.assertEqual(owners.rules[1], OwnerRule("/src/checkout/auth/", "identity", 4))
        self.assertEqual(owners.rules[3].team, "docs")
        self.assertEqual(len(owners.rules), 7)

    def test_matching_and_last_rule_wins(self):
        owners = parse_owners(SAMPLE)
        cases = {
            "src/checkout/cart.py": "payments",
            "src/checkout/auth/login.py": "identity",
            "src/checkout/auth/oauth/pkce.py": "identity",
            "src/checkout/auth/refund_tokens.py": "payments",  # exception after the broad rule
            "src/checkout/auth": "payments",  # the directory itself is not "below" it
            "db/migrations/0004_refunds.sql": "data",  # no slash: file name at any depth
            "docs/runbook.md": "docs",  # trailing slash, unanchored: any depth
            "src/checkout/docs/api.md": "docs",
            "deploy/prod/checkout.yaml": "platform",
            "deploy/checkout.yaml": "platform",  # "**/" also matches zero segments
            "deploy/prod/checkout.yml": "payments",
            "README.md": "docs",
            "src/README.md": "payments",  # leading slash anchors at the root
            "./src/checkout/auth/login.py": "identity",
        }
        for path, team in cases.items():
            with self.subTest(path=path):
                self.assertEqual(owners.team_for(path), team)

    def test_single_star_stays_in_one_segment(self):
        owners = parse_owners("/src/*.py @fernwick/payments\n/src/?/x.py @fernwick/routing\n")
        self.assertEqual(owners.team_for("src/app.py"), "payments")
        self.assertIsNone(owners.team_for("src/api/app.py"))
        self.assertEqual(owners.team_for("src/a/x.py"), "routing")
        self.assertIsNone(owners.team_for("lib/app.py"))

    def test_anchored_pattern_without_trailing_slash_matches_only_that_path(self):
        owners = parse_owners("/src/auth @fernwick/identity\n")
        self.assertEqual(owners.team_for("src/auth"), "identity")
        self.assertIsNone(owners.team_for("src/auth/login.py"))

    def test_invalid_rules(self):
        bad = {
            "*.py\n": "has no team",
            "*.py @fernwick/payments @fernwick/routing\n": "more than one team",
            "*.py samuel.okafor@fernwick.example.test\n": "is not a team",
            "*.py @fernwick/Payments\n": "is not a team",
            "/ @fernwick/payments\n": "empty pattern",
        }
        for text, message in bad.items():
            with self.subTest(text=text), self.assertRaises(ParseError) as ctx:
                parse_owners("# header\n" + text, source="checkout-api/OWNERS")
            self.assertIn(message, ctx.exception.message)
            self.assertEqual(ctx.exception.details, {"source": "checkout-api/OWNERS", "line": 2})


class SampleOwnersTest(LedgerTestCase):
    def test_load_owners(self):
        self.assertIsNone(load_owners(self.tmp / "OWNERS"))
        (self.tmp / "OWNERS").write_text("﻿* @fernwick/routing\n", encoding="utf-8")
        self.assertEqual(load_owners(self.tmp / "OWNERS").team_for("planner/solver.py"), "routing")

    def test_sample_repositories(self):
        checkout = make_repo(self.conn, "checkout-api")
        self.assertEqual(owners_path(self.settings, checkout), ROOT / "samples/repos/checkout-api/OWNERS")
        owners = load_owners(owners_path(self.settings, checkout))
        self.assertEqual(owners.team_for("src/payments/refunds.py"), "payments")
        self.assertEqual(owners.team_for("src/checkout/auth/session_store.py"), "identity")
        self.assertEqual(owners.team_for("Dockerfile"), "platform")
        routes = load_owners(ROOT / "samples/repos/route-planner/OWNERS")
        self.assertEqual(routes.team_for("planner/publish/kafka.py"), "tracking")
        self.assertEqual(routes.team_for("deploy/helm/values.yaml"), "platform")
        self.assertEqual(routes.team_for("planner/solver/vrp.py"), "routing")


class ResolveTeamTest(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.payments = make_team(self.conn, "payments")
        self.identity = make_team(self.conn, "identity")
        self.repo = make_repo(self.conn, "checkout-api", team=self.payments)
        self.owners = parse_owners("* @fernwick/payments\n/src/auth/ @fernwick/identity\n/legacy/ @fernwick/billing\n")

    def resolve(self, location, owners=None):
        return resolve_team_id(self.conn, self.repo, location, owners or self.owners)

    def test_owners_rule_picks_team(self):
        self.assertEqual(self.resolve(Location.code("src/auth/login.py", 3)), self.identity.id)
        self.assertEqual(self.resolve(Location.code("src/cart.py")), self.payments.id)

    def test_falls_back_to_repo_team(self):
        url = Location.endpoint("https://checkout.fernwick.example.test/login", "next")
        self.assertEqual(self.resolve(url), self.payments.id)
        self.assertEqual(self.resolve(Location.dependency("harbor-json", "2.3.1")), self.payments.id)
        self.assertEqual(resolve_team_id(self.conn, self.repo, Location.code("src/auth/x.py"), None), self.payments.id)
        empty = parse_owners("/docs/ @fernwick/identity\n")
        self.assertEqual(self.resolve(Location.code("src/auth/x.py"), empty), self.payments.id)

    def test_unknown_slug_logs_and_falls_back(self):
        with self.assertLogs("ledger.ownership.teams", "WARNING") as logs:
            self.assertEqual(self.resolve(Location.code("legacy/invoice.py")), self.payments.id)
        self.assertEqual(logs.records[0].getMessage(), "ownership.unknown_team")
        self.assertEqual(logs.records[0].team, "billing")


if __name__ == "__main__":
    unittest.main()

