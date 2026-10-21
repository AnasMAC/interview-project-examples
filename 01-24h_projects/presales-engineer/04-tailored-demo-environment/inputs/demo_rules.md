# Demo environment rules (fictional Lantern Solutions Engineering)

These rules govern the shared demo tenant `lantern-demo-eu`. They are authoritative for this exercise. "Demo date" means the date of the customer demo, here **2026-06-10**.

- **R1 — No customer data.** Only apps in the approved demo catalog may exist in the tenant: `DEMO-AND-SHOP`, `DEMO-IOS-SHOP`, `DEMO-WEB-CHECKOUT`, `DEMO-AND-CARE`, `DEMO-IOS-CARE`. Any app outside the catalog, and every scan, finding and integration linked to it or to a prospect or customer name, must be deleted before any demo. Personal names or email addresses from prospects and customers must never appear. Hiding an object in the dashboard is not enough.
- **R2 — Freshness.** For each demo app, the latest completed scan of each type (static, dynamic) must have completed no more than 14 days before the demo date. For 2026-06-10, this means on or after **2026-05-27 00:00 UTC**. Older scans may remain as history behind a newer fresh scan of the same type, for example for trend views. A stale latest scan must be rerun on the current demo build.
- **R3 — Integrations.** An integration may be shown only if it is enabled and its last successful sync is no more than 7 days before the demo date (on or after **2026-06-03 00:00 UTC**). Otherwise re-enable and test it, or leave it out of the agenda.
- **R4 — Status matches evidence.** (a) A `fixed` finding must not have been seen in the app's latest completed scan of the same type as the scan that last saw it. (b) A `confirmed` finding needs a non-empty `validated_by`. (c) A `false_positive` or `risk_accepted` finding needs a non-empty `status_reason`. Correct the status or the supporting field.
- **R5 — Honest coverage.** Every Android and iOS demo app needs both a fresh static and a fresh dynamic completed scan. If that is impossible, set the app's `coverage_note` to `static-only` and present it only as static coverage. An App Store-encrypted IPA supports static analysis only.
- **R6 — Timing.** Each demo keeps at least **10 minutes** of its booked slot for questions. Between back-to-back demos, the reset in R8 takes 10 minutes.
- **R7 — Feature stage.** Only GA features may be demonstrated as available. A setting with `feature_stage` other than `GA` must be disabled before a customer demo. An "exploring" item may be mentioned only as exploring, with no date.
- **R8 — Reset.** Before each demo, run the pre-demo check against a fresh tenant export. After each demo, revert any status changed live and clear saved filters. Record who ran the check and when.

The export fields are self-explanatory. `last_seen_scan` is the most recent scan that reported the finding. Treat timestamps as UTC.
