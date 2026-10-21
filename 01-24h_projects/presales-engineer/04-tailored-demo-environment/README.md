# Prepare a tailored demo and a clean demo environment

You are a Pre-Sales Engineer at the fictional vendor Lantern. Tomorrow, **2026-06-10**, you run two back-to-back demos from the shared demo tenant. Corvo Retail is a business audience: a CISO and a procurement manager. Medlo Health is a technical audience: a mobile engineering team. The last export of the tenant shows it was left in poor condition after an earlier evaluation. Prepare both demos and a clean, checkable environment. The scenario snapshot is **2026-06-09 15:00 UTC**; it is separate from your assessment deadline.

## Timing and setup

Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. Effort is visible through follow-through and verification.

Read:

- [Discovery notes](inputs/discovery_notes.md)
- [Product facts](inputs/product.md)
- [Demo environment rules](inputs/demo_rules.md)
- [Tenant export at 15:00 UTC](inputs/demo_tenant.json)
- [Tenant export after a teammate's reset at 19:00 UTC](inputs/demo_tenant_after_reset.json)

Baseline skills for this role:

- Application security concepts: SAST versus DAST, common mobile and web weaknesses, false positives and authenticated scanning.
- Mobile build types and CI/CD workflows.
- Reading JSON.
- Explaining technical topics to both business and engineering audiences.

Scripting is optional. A careful checklist applied by hand is acceptable. You need no Lantern account, live tenant or paid tool. All entities and facts are fictional and authoritative for this exercise. Outside research is optional and cannot affect marks.

## Core task

1. **Audit the tenant.** List every rule violation in `demo_tenant.json`, with the rule ID, object IDs, evidence and the specific fix. Note any objects that look suspicious but comply, with the reason.
2. **Build a reusable pre-demo check.** It must flag violations of R1–R5 and R7 in any export with this structure. A script, a spreadsheet with formulas, or a step-by-step checklist that another engineer could repeat are all acceptable. Run it on both exports. Show the result for each export, and state what still blocks the demos after the teammate's reset and how you would fix it.
3. **Write one demo plan per prospect.** Each plan includes:
   - an agenda with minute timings that respects R6;
   - the story you will tell, and why it fits this audience;
   - the exact tenant objects (app, scan, finding and integration IDs) you will show; use only objects that are compliant after your fixes;
   - three discovery questions to ask;
   - likely objections, with honest answers.

   Address every hard requirement and every request in the notes. For each one, state whether Lantern meets it, partly meets it or does not meet it, with product fact IDs.
4. **Draft one follow-up email per prospect**, at most 150 words each, labeled **draft; do not send**. Each email confirms what was shown, gives honest answers to open asks and proposes a next step that Lantern can actually support.

Do not promise features, dates, certifications or prices that the product facts do not support. Do not show or describe the leftover customer data beyond what is needed to remove it. Do not contact anyone or use any real system. Optional stretch: a one-page "demo-ready" status card for the account executive; it is not needed for full marks.

## Submission and acceptance

Submit an archive or repository containing:

- the tenant audit;
- the reusable check, its run instructions and its output for both exports;
- the two demo plans;
- the two follow-up drafts;
- a concise work log.

Any readable format is accepted. Include a 3–5 minute recorded walkthrough **or an equivalent accessible text walkthrough** of one tailoring decision and one check.

Acceptance:

- Every violation is traced to object IDs and a rule.
- Compliant edge cases are not flagged as errors.
- The check reproduces the same results when rerun, and works on the second export without edits.
- Each plan fits its slot and uses only clean objects.
- Unmet requests are stated plainly, with a supported alternative where one exists.
- Business and technical plans differ in substance, not only in wording.

Your work log records your priorities, one obstacle and how you responded, one validation or refinement, limits and a next step. No AI tool is provided: you may use any AI tool you already have. AI is allowed and encouraged for analysis, scripting, drafting and critique; tool choice is not graded. Check AI output against the inputs. Include a short AI-use note naming the tool and one output you accepted, corrected or rejected, with the reason. If you did not use AI, say so; do not invent an AI failure. Do not submit full prompt histories or personal account access.

Scoring: **usable result 40; accuracy/verification 25; prioritization 20; communication/handoff 15**. Full marks are possible on the core alone. No marks for volume, hours worked, software choice, AI detection or polished prose.
