# Campaign handoff, rules, and fixtures

Source C1, unapproved draft from a fictional teammate: “SignalDesk finds every vulnerability automatically. Save 80% of triage time. Start your free trial now.” Existing CTA opens an empty mail window. This draft is input to assess, not approved evidence.

Source C2, launch constraints: one landing experience; primary CTA requests a guided demo; no live service connection. Use a fictional address from `example.test` or an invented record ID only. A work contact, operations team size, and whether the team already collects findings are required. Name and marketing-updates choice are optional. An email-like value must contain one `@`, a nonempty local part, and a domain containing a dot; this exercise rule is not a production email validator. Do not demand production credentials, security files, phone numbers, or company-wide headcount.

Source C3, eligibility and capacity: an operations team of 3–20 inclusive with existing findings is eligible. Empty/invalid required fields stay on the form with a text explanation. Eligible requests consume the single remaining slot only after a valid confirmation; ineligible requests do not. Once full, show a non-promissory interest/waitlist path with separate explicit consent and no confirmed demo date. The demo coordinator owns confirmed requests and interest records, replying within two business days. A duplicate request from the same contact should show the existing request rather than consume another slot. Evaluate each test independently from three reserved slots, except T6 explicitly follows T1 in the same run. Marketing consent does not change eligibility.

Source C4, accessibility: use readable labels, meaningful CTA names, explicit required-field instructions, text errors next to the relevant field, and a logical reading/focus order. Avoid relying on color, animations, or images to carry essential information. Text wireflows may state reading/focus order and demonstrate how a keyboard/text user reaches every branch.

| Test ID | Contact | Ops team size | Existing findings | Marketing updates | Starting state |
| --- | --- | --- | --- | --- | --- |
| T1 | lead1@example.test | 8 | yes | no | Three slots reserved |
| T2 | missing-at.example.test | 8 | yes | no | Three slots reserved |
| T3 | small@example.test | 2 | yes | yes | Three slots reserved |
| T4 | new@example.test | 10 | no | no | Three slots reserved |
| T5 | large@example.test | 21 | yes | no | Three slots reserved |
| T6 | lead2@example.test | 12 | yes | yes | Run after T1, four slots reserved |

Source C5, seven-day synthetic baseline: 240 eligible landing sessions, 36 CTA starts, 12 completed valid requests. Counts share the same seven-day cohort; do not infer how many received a demo. Calculate start/session, valid-request/start, and valid-request/session rates. This baseline is for measurement design, not evidence of product effectiveness.

Source C6, test reset: record the reserved count before/after each test and reset to three except T6. Include one duplicate replay of T1 inside its test without consuming a second slot. No form should silently enroll anyone in marketing updates.
