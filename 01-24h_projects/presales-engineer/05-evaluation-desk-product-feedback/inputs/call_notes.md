# Evaluation notes (fictional)

Notes are in date order. Each customer-reported issue has an intake ID (I01–I09). The customer's description of an issue is what they believe; it is not a diagnosis. A note marked **internal** is not customer contact.

## N01 — 2026-05-27 — E5 Solenne Media — call with Theo (DevOps Engineer)

- Trial setup. Theo added the Lantern CLI to their GitLab pipeline. Every run exits with code 3. "Your CLI is broken in CI." Pipeline log attached to T-322. **I01**
- "We run everything through ServiceNow. Do you integrate with it? Not a must-have for the trial, but our security manager will ask." **I02**
- No success criteria agreed yet. No PoC dates set. Theo will wait for us before continuing.

## N02 — 2026-05-28 — E4 Brightwater Logistics — email from Amal (QA Lead)

- "When we move a Lantern ticket to `Ready for QA` in Jira, the status never changes in Lantern. Sync looks broken." Their Jira workflow uses custom status names. Lantern version at the time: 3.8.1. **I03**
- Amal: "Jira sync-back is nice to have. It is not one of our three success criteria."

## N03 — 2026-05-29 — E2 Kestrel Health — call with Rania (AppSec Lead)

Success criteria agreed:

- C1 Android app static and dynamic scan — **met**
- C2 iOS app static scan — **met**
- C3 Authenticated dynamic scan of the patient portal — **open**
- C4 Triage workflow review with the AppSec team using C3 results — **open**; cannot start before C3 results exist

Issues:

- The portal scan stops at the authenticator-app code screen and never reaches logged-in pages. Rania: "The scanner is broken." The recorded login uses Rania's own MFA-enabled account. **I04**
- "We use ServiceNow for vulnerability tickets. If ServiceNow is coming in Q3, I think we could sign this month." **I05**

## N04 — 2026-06-02 — E1 Orbis Pay — call with Karim (Mobile Security Lead)

Success criteria agreed:

- C1 Android static and dynamic results for the payments app — **met**
- C2 CycloneDX SBOM export — **met**
- C3 Jira ticket creation for high and critical findings — **met**
- C4 iOS dynamic analysis results — **open**
- C5 Findings visible in GitHub code scanning through SARIF upload — **open**

Issues:

- iOS dynamic results show `not run`. Karim uploaded the IPA of the current App Store release. **I06**
- GitHub code scanning rejects the SARIF file. The Android scan has 212 findings. **I07**

## N05 — 2026-06-04 — E3 Tamarind Retail — call with Leo (Platform Engineering Manager)

Success criteria agreed:

- C1 Android scan results — **met**
- C2 iOS scan results — **met**
- C3 Jira Cloud ticket sync — **met**
- C4 GitHub Actions gate using `--fail-on high` — **met**
- C5 Findings visible in GitHub code scanning through SARIF upload — **open**
- C6 Authenticated scan of the REST checkout API using its OpenAPI 3 file — **open**; scheduled by Leo for 2026-06-15, no issue reported

Issues:

- GitHub rejects the SARIF upload with a validation error. The Android scan has 143 findings. **I08**
- The platform team wants mutation-level testing of their GraphQL API. Leo: "Our CTO wants a date for GraphQL support." **I09**

## N06 — 2026-06-04 — internal — message from Malik (AE, E2 and E4)

"Kestrel will sign if ServiceNow lands in Q3. Product said they are looking at it. Just tell Rania Q3 so we keep momentum."

## N07 — 2026-06-05 — E1 Orbis Pay — email from Karim

Readout booked for Wednesday 2026-06-10 15:00 UTC (60 minutes). Karim wants C4 and C5 evidence or a clear status before then.

## N08 — 2026-06-05 — E4 Brightwater Logistics — email from Amal

Readout booked for Thursday 2026-06-11 10:00 UTC (60 minutes). Amal confirms C1–C3 are met. She would like to see Jira sync-back working at the readout if possible.
