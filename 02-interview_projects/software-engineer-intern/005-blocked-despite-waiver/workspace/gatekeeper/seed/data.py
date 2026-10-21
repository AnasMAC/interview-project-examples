"""Static demo data: teams, services, policy history and waivers.

The contract (ids, slugs, timezones, key and secret derivation, URLs) is
docs/architecture.md, "Seeded data contract". Times are relative to ANCHOR,
the world's "today".
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import NamedTuple

ANCHOR = datetime(2026, 12, 2, 11, 0, tzinfo=UTC)
HISTORY_DAYS = 84
CI_MOCK = "http://ci-mock:9100"
REVIEWER_KEYS = ("security-review", "grace.adeyemi")


class Team(NamedTuple):
    id: int
    slug: str
    name: str
    timezone: str
    ci: str  # "forgeline_v2" | "legacy"
    weight: int  # evaluations at --scale 1
    risk: float  # multiplies the base violation rates
    created_days: int  # days before ANCHOR
    services: str  # "slug:major.minor ..." (version line at the start of the history)


TEAMS = (
    Team(1, "payments-api", "Payments API", "Europe/London", "forgeline_v2", 1400, 1.0, 785,
         "payments-api:4.7 payments-webhooks:2.3 refunds-worker:1.9"),
    Team(2, "ledger-core", "Ledger Core", "Europe/London", "forgeline_v2", 900, 0.8, 770,
         "ledger-api:6.1 ledger-reconciler:3.4 journal-writer:3.0 balance-snapshots:1.2"),
    Team(3, "card-issuing", "Card Issuing", "Europe/Dublin", "forgeline_v2", 800, 1.1, 705,
         "card-api:5.2 card-tokenizer:2.8 issuing-processor:3.1 pin-service:1.4"),
    Team(4, "settlement-sg", "Settlement Singapore", "Asia/Singapore", "forgeline_v2", 650, 1.3,
         525, "settlement-engine:2.6 sgd-clearing:1.3 payout-scheduler:1.0"),
    Team(5, "fx-rates", "FX Rates", "Europe/London", "forgeline_v2", 500, 0.9, 645,
         "rates-api:3.2 rates-ingest:2.0 quote-cache:1.5"),
    Team(6, "risk-scoring", "Risk Scoring", "Europe/Berlin", "forgeline_v2", 700, 1.2, 615,
         "risk-api:2.4 risk-models:7.0 fraud-rules:1.8 scoring-worker:2.2"),
    Team(7, "kyc-platform", "KYC Platform", "Europe/Lisbon", "legacy", 450, 1.6, 595,
         "kyc-api:2.0 document-check:1.6 sanctions-screening:3.3"),
    Team(8, "treasury-tools", "Treasury Tools", "Europe/London", "legacy", 250, 1.5, 485,
         "treasury-ui:1.1 cash-forecast:0.9 liquidity-reports:2.0"),
    Team(9, "merchant-portal", "Merchant Portal", "America/New_York", "forgeline_v2", 900, 1.0,
         455, "merchant-web:8.3 merchant-api:3.6 onboarding-flow:2.1 statements-export:1.0"),
    Team(10, "data-pipelines", "Data Pipelines", "Europe/Warsaw", "legacy", 350, 1.7, 305,
         "event-loader:1.4 warehouse-sync:2.2 reporting-batch:0.7"),
    Team(11, "mobile-backend", "Mobile Backend", "Europe/London", "forgeline_v2", 650, 1.0, 70,
         "mobile-gateway:1.0 push-notifier:0.4 device-registry:0.2"),
    Team(12, "platform-infra", "Platform Infra", "Europe/London", "forgeline_v2", 450, 0.6, 790,
         "edge-proxy:1.18 secrets-broker:2.5 build-images:1.40"),
)

# (team, days before ANCHOR, author key, comment, overrides of seed.generate.policy_rules)
POLICIES = (
    ("payments-api", 778, "grace.adeyemi", "initial policy",
     {"signing": False, "sast_alias": True}),
    ("payments-api", 412, "grace.adeyemi", "require signed production releases",
     {"sast_alias": True}),
    ("payments-api", 150, "security-review", "rename to sast.new_high_max; sign main and release",
     {"signing_branches": ["main", "release/*"]}),
    ("payments-api", 38, "grace.adeyemi", "pass rate 0.98 after the October refunds incident",
     {"signing_branches": ["main", "release/*"], "pass_rate": 0.98}),
    ("ledger-core", 760, "grace.adeyemi", "initial policy", {"sast_alias": True}),
    ("ledger-core", 95, "security-review", "new high SAST findings block on main and release",
     {"sast_action": "block", "sast_branches": ["main", "release/*"]}),
    ("card-issuing", 700, "grace.adeyemi", "initial policy (PCI scope)",
     {"dep_max": "medium", "sast_alias": True}),
    ("settlement-sg", 520, "grace.adeyemi", "initial policy", {"sast_alias": True}),
    ("settlement-sg", 60, "security-review", "allow 2 new high SAST findings during remediation",
     {"sast_max": 2}),
    ("fx-rates", 640, "grace.adeyemi", "initial policy",
     {"tests_action": "warn", "sast_alias": True}),
    ("risk-scoring", 610, "grace.adeyemi", "initial policy",
     {"pass_rate": 0.9, "sast_alias": True}),
    ("risk-scoring", 20, "security-review", "models repo has a real test suite now", {}),
    ("kyc-platform", 590, "grace.adeyemi", "initial policy (legacy runner)",
     {"sast_alias": True, "signing": False}),
    ("treasury-tools", 480, "grace.adeyemi", "initial policy (legacy runner)",
     {"sast_alias": True, "tests_action": "warn", "signing": False}),
    ("merchant-portal", 450, "grace.adeyemi", "initial policy", {"sast_alias": True}),
    ("merchant-portal", 70, "security-review", "signing required for releases from main only",
     {"signing_branches": ["main"]}),
    ("data-pipelines", 300, "security-review", "initial policy (legacy runner)",
     {"sast_alias": True, "pass_rate": 0.9, "signing": False}),
    ("mobile-backend", 63, "grace.adeyemi", "first policy for the new team", {}),
    ("platform-infra", 785, "grace.adeyemi", "initial policy",
     {"dep_max": "medium", "sast_action": "block", "sast_alias": True}),
    ("platform-infra", 230, "grace.adeyemi", "signing for every environment",
     {"dep_max": "medium", "sast_action": "block", "signing_envs": None}),
)


class Waiver(NamedTuple):
    team: str
    service: str | None
    rule: str
    status: str
    created_days: float  # before ANCHOR
    expires_hours: float  # relative to ANCHOR (negative: in the past)
    reason: str
    note: str | None = None
    version_range: str | None = None
    revoked_days: float | None = None  # before ANCHOR
    advisory: tuple[str, str, str] | None = None  # package, version, id kept failing


WAIVERS = (
    Waiver("data-pipelines", "warehouse-sync", "dependency.max_severity", "expired", 80, -240,
           "pyarrowish 9.0 pins a vulnerable zlib; upgrade blocked on the warehouse driver",
           "ok until the driver upgrade lands"),
    Waiver("risk-scoring", "risk-models", "tests.min_pass_rate", "approved", 70, 432,
           "model regression suite is being rewritten, old tests are knowingly red",
           "keep the rewrite ticket linked"),
    Waiver("settlement-sg", "sgd-clearing", "sast.new_high_max", "expired", 50, -288,
           "two SAST highs are false positives on generated MEPS+ bindings", "re-check after"),
    Waiver("payments-api", "payments-api", "tests.min_pass_rate", "expired", 45, -600,
           "contract tests against the acquirer sandbox time out since its migration",
           "until the sandbox is fixed"),
    Waiver("ledger-core", "journal-writer", "dependency.max_severity", "revoked", 40, 240,
           "isodatum 1.2 advisory, fix needs the 3.x date handling refactor",
           "fixed in journal-writer 3.4.0, waiver no longer needed",
           ">=3.0.0", 18),
    Waiver("fx-rates", "rates-ingest", "secrets.allowed", "expired", 35, -480,
           "test fixture contains a revoked vendor sandbox token"),
    Waiver("payments-api", "refunds-worker", "sast.new_high_max", "expired", 60, -720,
           "deserialization finding is in dead code removed next sprint", "one sprint only"),
    Waiver("card-issuing", "card-tokenizer", "dependency.max_severity", "approved", 30, 55,
           "cryptobox 3.1 medium advisory; vendor fix due before the PCI audit", "approved"),
    Waiver("payments-api", "payments-webhooks", "secrets.allowed", "rejected", 25, 120,
           "the key in deploy/app.env is a staging key",
           "rotate the key instead; a waiver does not make a leaked secret safe"),
    Waiver("merchant-portal", "merchant-web", "dependency.max_severity", "revoked", 20, 480,
           "chartmint advisory rated medium by the vendor",
           "advisory re-scored critical upstream; upgrade chartmint", None, 4),
    Waiver("settlement-sg", "settlement-engine", "dependency.max_severity", "approved", 20, 40,
           "fixed tzshim release only after the MAS reporting freeze", "until the freeze ends"),
    Waiver("risk-scoring", "fraud-rules", "dependency.max_severity", "rejected", 15, 360,
           "yamlette critical advisory not reachable from our code",
           "reachability is not shown; upgrade, it is a patch release", "<2.0.0"),
    Waiver("mobile-backend", "push-notifier", "sast.new_high_max", "approved", 14, 384,
           "SAST flags the vendored push SDK, upstream ticket open", "approved"),
    Waiver("kyc-platform", "kyc-api", "dependency.max_severity", "approved", 12, 720,
           "pdfmint 0.9.2 used only for internal previews, replacement in progress",
           "2.5 line only", ">=2.5.0,<2.6.0", None, ("pdfmint", "0.9.2", "MBSA-2025-0310")),
    Waiver("ledger-core", None, "tests.min_pass_rate", "approved", 10, 480,
           "flaky reconciliation tests quarantined, tracked in LEDG-2291", "approved"),
    Waiver("payments-api", "payments-api", "dependency.max_severity", "approved", 9, 288,
           "ledgerkit 2.4.1 has no fixed release; upstream patch expected in 2.4.3",
           "approved for the 4.12 line only", ">=4.12.0,<4.13.0", None,
           ("ledgerkit", "2.4.1", "MBSA-2026-0141")),
    Waiver("platform-infra", "build-images", "dependency.max_severity", "approved", 8, 528,
           "base image openssl advisory, distro backport pending", "approved"),
    Waiver("merchant-portal", "statements-export", "signing.required", "approved", 6, 60,
           "signing key rotation in progress for the statements pipeline", "short waiver"),
    Waiver("kyc-platform", "document-check", "sast.new_high_max", "approved", 5, 36,
           "requested as sast.max_high: OCR wrapper findings under review", "approved"),
    Waiver("settlement-sg", "payout-scheduler", "tests.min_pass_rate", "approved", 3, 144,
           "holiday calendar tests fail until the 2027 calendar is published", "approved"),
    Waiver("data-pipelines", "event-loader", "tests.min_pass_rate", "pending", 2, 240,
           "Kafka integration tests flaky on the legacy runner"),
    Waiver("card-issuing", "pin-service", "signing.required", "pending", 1.2, 336,
           "HSM signing service migration this week"),
    Waiver("treasury-tools", None, "tests.min_pass_rate", "pending", 0.5, 720,
           "moving off the legacy runner, tests are being ported"),
)

PACKAGES = {
    "pypi": ("ledgerkit", "flaskwork", "pdfmint", "yamlette", "cryptobox", "tzshim",
             "isodatum", "money-units", "requestor", "pyarrowish"),
    "npm": ("chartmint", "fetchwell", "datefold", "qs-lite", "react-ledger", "formwise"),
}
NPM_TEAMS = ("merchant-portal", "mobile-backend")
SECRET_DETECTORS = ("generic-api-key", "aws-access-key", "private-key", "slack-webhook")


def seeded_key(name: str) -> str:
    return "gk_demo_" + hashlib.sha256(f"mossbank-seed:{name}".encode()).hexdigest()[:32]


def callback_secret(slug: str) -> str:
    digest = hashlib.sha256(f"mossbank-seed-secret:{slug}".encode()).hexdigest()[:12]
    return f"DEMO-whsec-{slug}-{digest}"
