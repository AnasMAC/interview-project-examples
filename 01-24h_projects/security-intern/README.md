# Security Intern: AI-enabled 24-hour exercise bank

Assign **one** exercise per candidate. The candidate receives an invitation email with a start link; their 24 hours begin when they click **Start**, which also unlocks the zip of the package's `candidate/` directory. Candidates are not expected to work the full 24 hours; the clock tests bounded execution and follow-through, not sleep sacrifice or scientific measurement of motivation.

| Exercise | Primary work | Reusable result |
| --- | --- | --- |
| [01 Scanner finding validation](01-scanner-validation/README.md) | Reproduce and disposition scanner claims | Local evidence replay and finding register |
| [02 Authorization review and repair](02-authorization-review/README.md) | Review identity, role and tenant boundaries | Small code repair and policy regression tests |
| [03 Incident triage from imperfect logs](03-incident-triage/README.md) | Correlate events and bound conclusions | Repeatable triage workflow tested on two windows |
| [04 Secrets and CI audit](04-secrets-ci-audit/README.md) | Apply policy to contextual configuration risks | Reusable offline audit with a second snapshot |
| [05 Download remediation verification](05-remediation-verification/README.md) | Test a proposed fix and repair its boundary | Working local fix and regression suite |
| [06 Android build review](06-android-build-review/README.md) | Static review of an Android build's manifest, config and code | Offline build checker rerun on the next release candidate |
| [07 Dependency advisory triage](07-dependency-advisory-triage/README.md) | Match advisories to components and justify exposure | Version-range matcher and triage register rerun on an updated SBOM |
| [08 Detection rule tuning](08-detection-rule-tuning/README.md) | Improve a noisy scanner rule against a labeled corpus | Precision/recall evaluator run on a holdout corpus |
| [09 Session token findings write-up](09-session-token-findings/README.md) | Confirm teammate notes and write engineering-ready reports | Replay runner reused to retest a developer patch |
| [10 Security review of an AI-generated password reset](10-ai-reset-flow-review/README.md) | Review AI-written auth logic against its claims and the policy | Repair, regression tests and a verdict on a proposed AI patch |

All entities, credentials, product facts and events are fictional assessment fixtures. Deliberately vulnerable training code and incomplete starting material are labeled in each brief; code makes no network connections, binds no ports and targets no real systems. Fixtures are authoritative; external research is optional and never required for marks.

Export **only the assigned package's `candidate/` directory**. Evaluator files are visible to repository readers: this private repository exercise bank is not a confidential test. Do not rely on secrecy; each evaluator guide includes an optional follow-up question that can check ownership if the candidate is invited to a later interview. Guides live in each package's `evaluator/README.md`; never include them in candidate exports.

No AI tool is provided; candidates may use their own, with a free/offline path and no purchases. AI is encouraged, tool brands are not graded, and no personal account access or complete prompt history is required. Full marks are available on core alone: usable result 40, accuracy/verification 25, prioritization 20, communication/handoff 15. Grade evidence and follow-through, not polish, output volume, hours worked or AI detection. Recruiters may use accessible text walkthroughs instead of recordings. No production work, public deployment or company deliverable is requested.
