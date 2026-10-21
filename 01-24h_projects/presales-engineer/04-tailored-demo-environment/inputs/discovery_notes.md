# Discovery notes for the 2026-06-10 demos

Account executive Noor recorded these notes from discovery calls. They summarize what the prospects said; they do not quote the prospects. Both prospects are fictional. Treat every note as a customer statement unless it is marked as Noor's own comment.

## Corvo Retail — demo 2026-06-10 10:00–10:45 UTC (video call)

- **C1:** The attendees are Lina Haddad, CISO, and Tomás Ferreira, Procurement Manager. No engineers will attend.
- **C2:** Corvo has an Android shopping app, an iOS shopping app and a web checkout. They release monthly.
- **C3:** Today Corvo pays for two external manual penetration tests a year, at USD 18,000 each. Findings arrive as PDF reports months apart. The board now wants a quarterly view of the app risk trend.
- **C4:** Hard requirement: application data must stay in the EU.
- **C5:** Hard requirement from Tomás: under procurement policy VR-2, any vendor that processes app data must provide an **ISO 27001 certificate**. Corvo's vendor-risk committee can approve exceptions case by case, based on other assurance evidence.
- **C6:** About 15 security and development staff would sign in. Lina wants single sign-on.
- **C7:** Lina asked whether Lantern would "replace our pentests and certify that the checkout is PCI DSS compliant."
- **C8 (Noor's comment):** "Lina will ask about price. I'll handle that after the demo; please don't quote numbers."

## Medlo Health — demo 2026-06-10 11:00–11:40 UTC (video call)

- **M1:** The attendees are Sami Ouali, Mobile Engineering Lead, and Rita Mendes, Android developer. Yan Costa, Backend Lead, may join for the last 15 minutes.
- **M2:** Medlo builds a patient app in Kotlin (Android) and Swift (iOS) with GitHub Actions. Their CI already produces an ad-hoc signed IPA for QA, as well as the App Store build.
- **M3:** Sami wants pull requests to fail only on **new** high or critical findings. Their CI policy requires every PR check to finish within **30 minutes**.
- **M4:** Medlo's previous tool produced many false positives, and developers stopped reading its results. Rita wants to mark a false positive once and not have it fail builds again.
- **M5:** Most of the issues their manual testers find are runtime behavior on iOS, so iOS dynamic analysis is a hard requirement.
- **M6:** Yan's patient API is **GraphQL**. He wants testing for introspection exposure and query-depth abuse.
- **M7:** All test accounts and builds use synthetic patient data. Medlo is in the EU and asked which region data would be stored in.
