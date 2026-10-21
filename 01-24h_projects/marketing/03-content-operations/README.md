# An educational campaign that can ship

QueueHarbor is a fictional workspace for assigning owners to security findings. A short training session has useful practical advice, but its draft snippets overstate the product. Turn the local sources into a coherent educational campaign and a reusable editorial/distribution system that survives review delays and source changes.

## Time, access, and boundaries

Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. The clock tests bounded execution and verification, not motivation or sleep sacrifice.

No AI tool is provided: you may use any AI tool you already have. AI is allowed and encouraged for repurposing, critique, organization, automation, and QA. No paid tools are needed. Use free/offline documents, slides, or spreadsheets; tool choice is not graded. Code, generated images, branded assets, and accounts are unnecessary. Check AI output against the local sources. Optional outside research does not affect marks or fictional facts. Do not post, email, publish, run ads, create accounts, or use real addresses/customer information.

Baseline skills: plain writing, basic tables, organizing a small schedule. The supplied glossary provides all security terminology needed.

## Inputs and setup

Open Markdown locally and import CSVs with headers. Keep source/asset IDs in your campaign and tracker.

- [Training transcript, product facts, glossary](inputs/source-session.md).
- [Campaign constraints, team policy, and new source note](inputs/operations-brief.md).
- [Unapproved draft snippets](inputs/draft-snippets.csv).
- [Existing work calendar](inputs/calendar.csv).

Sources are synthetic and authoritative only for this assessment. Product facts P1–P4 take precedence over draft snippets. Educational advice is general exercise material, not a real security assessment or guarantee.

## Core work

1. Choose one audience problem and a single educational takeaway from the transcript. Define the connection between the content and the approved demo CTA, without turning education into an unsupported product guarantee.
2. Create **four connected assets**: one social post (at most 120 words); a five-slide text carousel (at most 40 words per slide); one email (at most 150 words); and a landing FAQ with three short answers (at most 70 words each). Supply text descriptions/reading order for the carousel; no images required. Each asset needs a distinct channel purpose and a source map. Preserve one consistent CTA destination and use fictional links from the brief. You may rewrite or discard draft snippets; log decisions for all six.
3. Build a reusable editorial/distribution system for these assets with asset ID, audience, source/version, channel, owner, dependency, review status, approval owner, intended campaign time, CTA target, accessibility check, and distribution permission. Document how new content enters the system and what happens when a reviewer is unavailable, a source changes, or a CTA breaks. A spreadsheet or explicit rule-based table is enough; no integrations or actual publishing.
4. Resolve calendar collisions and review-capacity constraints. Produce a feasible rehearsal schedule with a fallback that does not silently publish unapproved content. Explain a specific deprioritization. Campaign days are simulated: you do not need to wait for a timestamp.
5. Demonstrate the system with four tabletop QA cases: unsupported snippet, broken CTA, missing carousel reading order, and delayed review. Record starting state, expected/actual routing or permission, owner, and fix/retest. Then ingest the supplied new source note N1 as a fresh FAQ update using the same workflow, propagate its effect to at least one other asset, and replay the affected checks. This is the second-input test of reusability.

Keep scope to four core assets and one N1 update. Optional stretch: a fifth channel or automated tracker; not required for full marks.

## Deliverables and acceptance

Submit an archive or repository with an opening file, editable four assets, source map and snippet decisions, editorial system and rehearsal schedule, QA/retest log, and concise handoff. A teammate should be able to:

- Trace educational and product statements to source IDs and distinguish advice from product capability.
- Follow the same useful takeaway and demo request across all four assets.
- Determine what can be distributed, when, by whom, and after which approvals without guessing.
- Replay all four failure cases and the N1 update, seeing actual state changes, dependencies, and retests.
- Read all essential carousel information as text and find usable CTA/error fallback instructions.

Include a short decision/work log: priorities, one obstacle/response, one validation/refinement, limits, next step. Include a short AI-use note naming one accepted/corrected/rejected output and why; no fabricated failure, personal account access, or full prompt history. Provide a **3–5-minute recording or equivalent concise text walkthrough**, equally acceptable.

Working approvals and traceable content take priority over visual polish.

## Scoring

Weights: usable result **40**, accuracy/verification **25**, prioritization **20**, communication/handoff **15**, total 100. Full marks possible on core alone. Do not expect marks for hours worked, AI-detector results, writing volume, or prose polish.
