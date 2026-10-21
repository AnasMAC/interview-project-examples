# Authorization review and repair

The fictional Workboard app lets editors and administrators change task status. A teammate added a shortcut for administrators and now wants a security review. Repair the policy boundary and build a compact regression suite that another teammate can reuse.

**Deliberately vulnerable training code:** the starter omits policy checks. It operates on an in-memory dictionary, opens no service and makes no network calls. Do not reuse it in production.

## Inputs and setup

- [Application and replay command](inputs/app.py).
- [Actors and task state](inputs/state.json).
- [Normal requests](inputs/requests.json).
- [Authoritative policy](inputs/policy.md).

Baseline skills: read basic Python functions/dictionaries, understand roles and tenants, write assertions. Python 3.10+ standard library only. From this project directory, run `python3 inputs/app.py inputs/requests.json` (or `python` if that is your local command). JSON output shows responses and final task state. Requests use actor_id, task_id, status and request_id; state starts fresh on each CLI run.

## Core work and acceptance

1. Review the code against every policy rule, including ordinary authorized behavior. Submit a small finding/evidence table with observed behavior, policy reference, affected actor/task and priority. Prove defects by executing the original version; preserve its evidence before editing.
2. Repair `app.py` without changing the policy or supplied original data. Add a runnable regression suite using fresh state per case. Require at least eight independent cases covering valid updates in both tenants, denied viewer, cross-tenant administrator, inactive identity, invalid status, missing task and unknown identity. There is no read endpoint to build.
3. Prove that denied operations leave all task data unchanged. Show before/after behavior, not only return codes. Your suite must fail with the original vulnerable code and pass with your repair; record which assertions fail on the original. Include at least one normal update to each tenant to detect an overbroad deny-all repair.
4. Provide a concise reviewer handoff: root cause, smallest defensible repair, limits and next step. No framework, database, authentication server or new product feature is required.

Acceptance: a reviewer can run tests with one documented offline command, see real state transitions, verify every policy rule and use original exploit evidence to distinguish a repair from disabling the app. Keep scope to update authorization; do not add unrelated dependencies or endpoints. Optional stretch: improve structured audit output, not needed for full marks.

## Submission, AI and timing

Submit an archive or repository containing runnable artifacts, source/evidence references, captured verification output and a concise walkthrough (up to five minutes recording **or equivalent accessible text**). Include exact commands and tool versions. Add a short decision/work log recording prioritization, one obstacle and response, one validation/refinement, limits and next step. Add an AI-use note with one accepted, corrected or rejected output and how you checked it; if no AI was used, say so. Never fabricate an AI failure.

No AI tool is provided: you may use any AI tool you already have. AI is allowed and encouraged for coding, drafting, research, automation and critique. Verify AI output. Tool choice is not graded; free/offline tools are supported, no purchases or personal account access are needed. Synthetic fixtures are the authoritative universe; outside research is optional and cannot affect marks.

Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. The clock tests bounded execution, follow-through and verification, not willingness to sacrifice sleep. Do only this assigned exercise. Full marks are possible on core alone: usable result **40**, accuracy/verification **25**, prioritization **20**, communication/handoff **15**. No AI-detector, writing-volume or prose-polish scoring. Work is an exercise submission, not a company deliverable: no external targets, outreach, production actions or public deployment.
