# REQ-0221: SLA badges for exposures

| | |
|---|---|
| From | Freya Lindqvist (product) |
| Date | 2026-11-02 |
| Customers | Harborview Bank (audit requirement), Orchid Grid |
| Priority | Medium; Harborview's auditors visit in December |
| Status | Ready for design |

## Problem

Customers fix exposures against internal deadlines: Harborview's policy is
"critical in 3 days, high in 7, medium in 30". Atlas shows when an exposure
opened, but not whether it is late, so their teams keep a spreadsheet next
to the dashboard. The auditors want to see, per exposure, the due date and
whether it was met.

## What we want

- A due date per open exposure: `opened_at` plus an SLA that depends on
  severity. Defaults: critical 3 days, high 7, medium 30, low 90. Each org can
  override the four values.
- Three states: **on track**, **due soon** (less than 24 hours left), and
  **overdue**. Resolved exposures keep a "met" / "missed" flag (resolved
  before or after the due date) for the audit.
- Badges on the dashboard: asset list (worst state among the asset's open
  exposures), asset detail (per exposure, with the due date) and the
  exposures page, where it should be possible to show only overdue ones.
- The API returns the due date and state on exposures and can filter by
  state (`GET /api/v1/exposures/?sla=overdue`).

## Open questions (please decide and explain)

- If an exposure's severity changes (a certificate goes from "expiring" to
  "expired" and becomes critical), does the clock restart, keep the original
  due date, or take the earlier of the two?
- An exposure that resolves and opens again a week later: new due date or
  the old one?
- Due dates are shown in the org's timezone. Harborview is in Toronto and
  just changed to winter time; "3 days" is 72 hours either way, right? Make
  sure the date shown does not jump by a day around a DST change.
- Business days are explicitly out of scope for now.

## Done when

- SLA values per org (migration with the defaults), due date and state in the
  API with the filter, badges on the three dashboard pages.
- Tests for the boundaries (exactly at the due time), severity changes and
  one exposure crossing a DST change.
