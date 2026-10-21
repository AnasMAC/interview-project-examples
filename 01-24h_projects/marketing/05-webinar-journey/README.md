# A webinar journey with no dead ends

The fictional product HarborBoard is hosting a small educational webinar about assigning owners to existing security findings. A draft event handoff has inconsistent time copy and no safe handling for duplicates, cancellations, consent, or recording delays. Build an offline registration/nurture journey and an operational state system a teammate can run.

## Time, access, and boundaries

Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. The deadline tests bounded execution and follow-through, not motivation or sacrificed sleep. Event times are simulated fixture data; do not wait for them in real time.

No AI tool is provided: you may use any AI tool you already have. AI is allowed and encouraged for state design, templates, critique, automation, and checking. Do not buy tools. Free/offline text, slides, or spreadsheets work; tool choice and coding are not graded. Check AI output against local event policy. Optional research adds no marks and cannot prove fictional facts. Do not send messages, collect actual contacts, publish, create accounts, or connect to an event platform.

Baseline skills: clear writing, simple tables, following a time-ordered log. No security, event-platform, programming, or legal expertise is needed. The local glossary and policy are complete for this exercise.

## Inputs and setup

Open Markdown locally; import CSVs with headers. Keep contact/event IDs and fictional `example.test` addresses as test data only.

- [Event facts, policy, and glossary](inputs/event-policy.md).
- [Registration event log](inputs/registration-events.csv).
- [Attendance and recording status](inputs/attendance.csv).
- [Draft copy, CTA inventory, and QA prompts](inputs/draft-handoff.md).

Use policy facts over draft copy. Every product/event claim is fictional. Unknown attendance or asset readiness must be held rather than guessed.

## Core work

1. Build an offline registration experience with explicit fields, consent choices, event time/timezone, accessible reading order, CTA destination and follow-through. A linked slide prototype, numbered text wireflow with a transition table, or no-code offline prototype is equally acceptable. Include invalid contact, confirmed seat, full/waitlist, closed registration, and cancellation paths; a reviewer must be able to follow them without accounts.
2. Create a reusable lifecycle system with stable contact identity, current state, seat count, trigger, owner, allowed next action, message eligibility, marketing-consent state, and checks. Cover waitlist offer/acceptance/expiry, duplicate request, cancellation, event reminders, and attended/no-show follow-up. Keep operational event messages separate from marketing permission under the supplied policy. A rule table plus editable ledger is enough; no integration required.
3. Process all registration log events in order and join attendance. Produce a final contact/state ledger and message queue showing what would be sent/held, why, by whom, and when. Include the recording-not-ready constraint. Keep raw records unchanged. Event count is not contact count; a duplicate must not consume another seat.
4. Write six short templates (at most 100 words each): confirmed registration, waitlist status, waitlist offer, cancellation acknowledgment, pre-event reminder, and post-event follow-up. The final template must have explicit attended/no-show and recording-ready/held variants. State CTA, audience eligibility, owner, and trigger next to each; no actual sending. You may use short variable fields such as contact ID or displayed event time, with their source defined.
5. Demonstrate at least six tabletop checks covering duplicate, invalid contact, capacity/promotion, cancellation/reminder suppression, marketing opt-out, and recording hold. Record expected/actual state, seat count/message permission, pass/fail, fix and retest. Then use the supplied expiry QA case as a second scenario in the **same** rule system and rerun affected capacity/offer checks. Avoid silently changing rules to force an answer.

Core scope is one event, a small ledger, six templates, and a repeatable state/QA system. Optional stretch: calendar file or automation; not necessary for full marks.

## Submission and acceptance

Submit an archive or repository with opening instructions, editable offline experience/state rules, processed contact ledger and message queue, six templates, QA/second-scenario log, and handoff. A teammate should be able to:

- Replay the original ordered log without overbooking, duplicate seats, contradictory confirmations, or silent consent changes.
- Follow every required registration branch and understand displayed timezone and next-step ownership.
- Determine reminder/follow-up eligibility and preserve opt-outs while honoring the exercise's operational-message policy.
- Hold unavailable recording links and replay the expiry scenario using the same rules.
- Find six expected/actual checks and at least one documented refinement/retest.

Include a concise decision/work log with priorities, one obstacle/response, one validation/refinement, limits and next step. Include a short AI-use note with one accepted/corrected/rejected output and reason, without fabricating a failure, sharing accounts, or full prompt histories. Provide a **3–5-minute recording or equivalent concise text walkthrough**, equally acceptable.

Prioritize state correctness and usable handoff over styling.

## Scoring

Weights: usable result **40**, accuracy/verification **25**, prioritization **20**, communication/handoff **15**, total 100. Core alone can earn full marks; no hours-worked, AI-detector, writing-volume, or prose-polish score.
