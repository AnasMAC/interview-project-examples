# SE desk rules (fictional)

The snapshot is **Monday 2026-06-08 08:00 UTC**. Business days are Monday to Friday. There are no holidays in June 2026.

## R1 — Capacity

You have **16 SE hours** from Monday 2026-06-08 to Friday 2026-06-12. Booked meetings count against this budget. Use the estimates in `se_backlog.csv` as given: do not shorten or split a task. Leftover time is buffer.

## R2 — Evaluation priority score

Score = urgency + value + risk. Higher scores come first.

- **Urgency:** PoC end date 0–3 business days after the snapshot date = 3; 4–7 business days = 2; later = 1; no PoC end date = 0.
- **Value:** estimated ARR of USD 60,000 or more = 3; USD 30,000–59,999 = 2; under USD 30,000 = 1.
- **Risk:** +2 if at least one agreed success criterion is **blocked** (R3). +1 if the last customer contact is 7 or more calendar days before the snapshot date. Both can apply. Internal notes are not customer contact.
- **Tie-break:** earlier PoC end date first, then higher ARR.

## R3 — Blocked criteria and status tiers

A criterion is **blocked** when it cannot be met until an open customer-reported issue is resolved, of any issue type. A criterion that is simply scheduled, or depends only on a blocked criterion, does not add extra risk points. The `ae_blocker_field` in `evaluations.csv` is free text typed by account executives. It is not evidence; use the call notes.

Tiers for the sales manager:

- **At risk:** at least one blocked success criterion.
- **Watch:** not at risk, and either the last customer contact is 7 or more calendar days old or no success criteria are agreed.
- **On track:** everything else.

## R4 — Weekly plan

1. Schedule mandatory work first:
   - booked meetings;
   - tasks that unblock a blocked criterion for an evaluation whose PoC ends within 7 business days of the snapshot, including the rerun or review needed to show the criterion is met;
   - readout preparation for a readout booked this week;
   - a retest of an already-fixed issue before that evaluation's readout this week;
   - a technical follow-up email for every evaluation whose last customer contact is 7 or more calendar days old;
   - filing product feedback (R7) for each distinct bug or missing capability. None is filed yet.
2. Then add optional tasks in evaluation priority order, and in backlog order within one evaluation, while the whole task still fits the budget.
3. List every task you defer, with the reason.

## R5 — Ownership

- **SE (you):** technical configuration and enablement, success-criteria evidence, readouts, technical follow-ups and product feedback.
- **Support:** reproduction and fixing of product bugs. You link to the ticket; you do not promise a fix.
- **Product:** roadmap and dates.
- **AE:** pricing, contract and commercial terms.

## R6 — Issue types

Give every customer-reported issue exactly one type:

- **Bug:** the product does not behave as documented, confirmed by evidence.
- **Missing capability:** the customer asks for something the product facts say it does not do.
- **Config or usage:** the product behaves as documented, and the issue comes from setup or input.
- **Already fixed:** a documented release fixes it. Retest before calling it resolved.
- **Duplicate:** the same underlying problem or request as an earlier report. The earliest report is canonical; link the duplicate to it. Do not count a duplicate twice.

The customer's label and the ticket's `type_as_reported` are not classifications.

## R7 — Product feedback entry template

File one entry per distinct bug or missing capability, merging duplicates:

- Title
- Type (bug or missing capability)
- Problem statement: the customer outcome blocked, not a proposed solution
- Evidence: note IDs, issue IDs, ticket IDs
- Affected evaluations
- ARR at stake: sum of the estimated ARR of the distinct affected evaluations
- Current workaround and its limit
- Requested by and date
- No promised release, quarter or date

## R8 — Customer drafts

Label every customer-facing message **draft; do not send**. Use only product facts. Do not promise a feature, date, discount or fix. Do not request credentials by email; ask the customer to configure a test account or token in their own tenant.
