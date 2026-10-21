# Orchid Pay × Lantern PoC — agreed success criteria (v2)

Agreed at kickoff on **2026-06-01** by Dalia (Orchid AppSec Lead) and Sami (Lantern sales engineer). PoC window: **2026-06-01 to 2026-06-14** inclusive. In scope: `orchid-wallet-android`, `orchid-wallet-ios` and `orchid-portal-web` (https://portal.orchid.test). All parties, apps and hosts are fictional.

## Verdict rules

- **Met:** the evidence shows the target was reached by the readout snapshot.
- **Not met:** the evidence shows the target was not reached, whatever the cause. Record the cause separately; a customer-side cause does not turn a miss into a pass.
- **Inconclusive:** the test defined for the criterion was not performed as specified, so the evidence shows neither a pass nor a miss.

Measure at the readout snapshot, **2026-06-15 09:00 UTC**, using both exports and the PoC log.

## Measurement rules for findings

- One finding = one `fingerprint`. Count distinct fingerprints, not export rows.
- A finding's current status is its status in the **latest export that contains it**. A finding missing from a later export keeps its earlier status and is labeled *not retested* (P4).
- **Triaged** = status `confirmed`, `false_positive`, `risk_accepted` or `fixed`. Status `open` is untriaged.

## Criteria

| ID | Criterion | Target |
| --- | --- | --- |
| C1 | CI automation | Each mobile app has at least one scan **triggered from Orchid's GitLab CI** that completes, and the job result matches `--fail-on high` (P5). |
| C2 | Mobile dynamic coverage | Each mobile app has at least one completed scan that includes **dynamic** analysis. |
| C3 | Authenticated web coverage | At least one completed web scan is authenticated and reaches pages under `/account/`. |
| C4 | Triage of serious findings | At least **80%** of distinct `high` and `critical` findings are triaged. |
| C5 | Signal quality | Among distinct triaged findings of all severities, the `false_positive` share is **at most 20%**. |
| C6 | Jira two-way sync | At least one Lantern → Jira status change **and** at least one Jira → Lantern status change through a **mapped** Jira status (P6). |

Percentages: show numerator, denominator and the result rounded to two decimal places.
