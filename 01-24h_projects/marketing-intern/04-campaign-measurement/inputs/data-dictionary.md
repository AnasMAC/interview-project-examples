# TriageLane facts and measurement dictionary

Fictional product: **P1**, TriageLane organizes manually uploaded findings and assigns owners; no automated discovery or repair. **P2**, the CTA requests a 20-minute guided synthetic demo, not an instant trial. **P3**, target audience is operations teams with 3–20 people already collecting findings. No price, market superiority, or quantified customer benefit is approved.

The baseline is a synthetic seven-day acquisition cohort; refresh contains two later cohort days plus re-exported rows. All aggregates use the same attribution window: requests and qualification recorded within seven days of the session's cohort date. Both exports are final for that window. Cohorts are independent and additive; counts are events/sessions, not unique people across days.

| Field | Rule |
| --- | --- |
| import_id | Unique row in an export; never use alone to deduplicate |
| source_record_id | Stable source record across exports; identical re-export is a duplicate, keep one |
| cohort_date | Synthetic session-cohort date; not the candidate's deadline |
| campaign | `search`, `newsletter`, or empty; empty means unattributed, not zero activity |
| sessions | Eligible landing sessions attributed to that cohort/campaign |
| cta_starts | CTA form starts in those sessions |
| valid_requests | Completed valid demo requests from those starts |
| qualified_requests | Subset of valid requests meeting P3; do not add them to valid requests |
| spend | Synthetic attributable acquisition spend in EUR for that record; not revenue |
| currency | Must be EUR in this exercise; do not convert an unknown currency |
| tracking_status | `ok` or `missing_campaign`; advisory check, not permission to delete valid unattributed counts |

**M1 — validation.** Counts/spend are nonnegative, integer counts, supported currency, and `sessions ≥ cta_starts ≥ valid_requests ≥ qualified_requests`. Quarantine hierarchy/currency/count failures, preserving all raw values. Exact source-record duplicates keep one and contribute spend once; differing values for the same ID require quarantine/escalation, not arbitrary latest-wins (none are intentionally provided). A missing campaign retains valid counts under an unattributed bucket. Data steward Ada owns anomalies; acquisition owner Bo owns campaign/experiment decisions; both names are fictional.

**M2 — rates.** Sum numerator/denominator first, then divide; do not average row percentages. CTA-start rate = starts/sessions. Request rate = valid requests/sessions. Qualified rate = qualified requests/sessions. Request-to-qualified rate is optional and uses qualified/valid. Rate output may round to two decimals while calculations retain precision.

**M3 — cost.** Spend/request = attributable spend/valid requests; spend/qualified = attributable spend/qualified requests. Undefined zero-denominator output is `N/A` with a reason, never infinity or an invented zero conversion cost. Unattributed row spend of 0 is a source value, not proof there was no acquisition cost; flag that limitation. Overall valid-data cost uses included attributable spend and all included valid outcomes and must carry the unattributed limitation. Excluded/quarantined spend is disclosed separately; it cannot be reconciled into campaign metrics without fixing its source.

Glossary: **cohort** = records grouped by the originating session date and attribution window. **Funnel** = progression from session to start to request to qualified request. **Attribution** = assigning activity to a campaign using its source tag; missing tags limit assignment. **Guardrail** = an outcome that should not deteriorate while improving the primary metric. **Hypothesis** = a testable explanation, not an observed effect. **Quarantine** = retaining data outside calculations pending a source fix. **Incremental** = valid new records added by refresh, excluding re-exports. **Combined** = unique valid records across both files.
