# Scanner finding validation

You are helping the fictional CedarScan team decide which alerts deserve engineering attention. A scanner produced four claims about a tiny report preview application. Validate them using the supplied local model, and turn the results into a replayable evidence pack. Do not assume the scanner is right or that failure to reproduce proves safety.

This is deliberately vulnerable training code. It runs entirely in memory, opens no files outside its inputs and creates no server. Only assess these fixtures. All facts are fictional; outside research is optional and cannot affect marks.

## Inputs and setup

- [Application and replay CLI](inputs/lab.py): inspect `respond`; edit or add request files to exercise it. Do not repair the app for this exercise.
- [Scanner alerts](inputs/alerts.json): unverified assertions with stable finding IDs.
- [Application contract](inputs/contract.md): policy and model limitations.
- [Initial requests](inputs/requests.json): three normal requests, not a security test suite.

Baseline skills: read short Python, understand request/response and basic authorization, record evidence. Use Python 3.10+; no installation beyond Python or dependencies. From this project directory run `python3 inputs/lab.py inputs/requests.json`. If `python3` is unavailable try `python`. Output is one JSON array. Request fields are explained in the contract.

## Core work

1. Disposition all four alerts as confirmed, refuted in this model, or unresolved with a precise limitation. Cite finding IDs, request IDs, code locations and output evidence. Separate reachability, impact and severity; choose the top two actions under the contract's resource limit.
2. Build a reusable evidence runner/checker with your request corpus and assertions. It must fail visibly if an observed behavior changes, include at least two legitimate controls and two adversarial probes, and run with one documented command. A small Python script is enough; no framework is required. Preserve the original lab behavior.
3. Refine at least one initial hypothesis after a check, or document a check that strengthened it. Supply an engineering-ready reproduction for the highest-priority confirmed issue and explain what evidence is still missing.

Acceptance: another reviewer can run the evidence pack offline, see actual app output rather than prose predictions, map every alert to evidence and distinguish a model limit from a refutation. The checker must assert returned status/body or header values, not merely print requests. No browser rendering or actual HTTP behavior can be proven by this model.

## Deliver and timing

Submit an archive or repository with your runner, requests, captured output, a concise finding register and a short walkthrough (up to five minutes recording **or equivalent accessible text**). Include commands and Python version. Add a decision/work log with prioritization, one obstacle and response, one validation/refinement, limits and next step. Include a brief AI-use note describing one accepted, corrected or rejected output and how you checked it; if you used no AI, say so, and never fabricate an AI mistake.

No AI tool is provided: you may use any AI tool you already have. AI is allowed and encouraged for coding, drafting, critique and research. Verify its output; tool choice is not graded. Free/offline tools suffice and no purchase is needed.

Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. Effort is judged through follow-through and verification, not writing volume. Do only this assigned exercise. Optional stretch: suggest an integration test outside the model; not required for full marks.

Published weights: usable result **40**, accuracy/verification **25**, prioritization **20**, communication/handoff **15**. Full marks are possible on core alone; no AI-detector or prose-polish scoring. Submit exercise work only: no scanning external targets, contacting others or publishing.
