# Response rules and context

## Scenario

- Prospect: fictional **Northwind Ledger**, an EU payments company. Procurement contact: **Lina**.
- Questionnaire received **2026-06-08 09:00 UTC**. Addendum received **2026-06-10 09:00 UTC**. Response due **2026-06-15 17:00 UTC**.
- Lantern account executive: **Noor**. You are the solutions engineer who owns the technical answers.

## Source precedence

1. `product.md` (P-IDs) is authoritative and overrides everything else.
2. `answer_library.csv` entries may be reused only when they agree with `product.md`. A newer library date does not make an entry correct.
3. Notes from calls or hints are context for the gap summary only. They never change a product answer.

## Answer categories

Give every question exactly one category. Apply the first rule that matches:

1. **Needs-escalation:** the question concerns contract, legal, pricing or discount terms (P16), or `product.md` does not cover it. Do not answer the substance; name the owner.
2. **Needs-NDA:** the question asks for a document that is available only under NDA. Say what exists and that it will be shared after an NDA.
3. **Roadmap-no-commitment:** the capability is listed in P15. Use the approved P15 wording only.
4. **Yes:** fully supported today on the proposed Enterprise plan.
5. **Partial:** supported with a limitation, condition or workaround. The answer must state it.
6. **No:** not supported. You may mention a genuine alternative, but do not imply it meets the requirement.

The category describes Lantern's capability only. If Northwind later accepts an equivalent control, record that in the gap summary as **Accepted equivalent**. Never change the category to reflect acceptance.

## Writing limits

- Each answer is at most **60 words** and cites at least one P-ID.
- Never state or imply a delivery date for any capability, never claim a certification Lantern does not hold, and never use “guarantee” about detection or security outcomes.

## Owners and approvals

| Topic | Owner | What they do |
| --- | --- | --- |
| Contract, liability, SLA, DPA changes | Hana (Legal) | Approves or declines contract terms |
| Release of NDA documents (SOC 2, penetration test summary) | Karim (Compliance) | Confirms NDA is signed, then releases |
| Pricing, discounts, bid/no-bid | Noor (Account executive) | Commercial decisions |
| Any roadmap statement beyond the P15 approved wording; facts missing from `product.md` | Yasmin (Product) | Confirms or supplies wording |

## Northwind's evaluation rules (from the RFP cover letter)

- A **must** answered No, or Roadmap-no-commitment, disqualifies the response unless Northwind's security architect accepts a documented equivalent control **in writing** before award.
- **Partial** on a must is acceptable only if Northwind accepts the stated condition.
- Should and info answers are scored but cannot disqualify.

## Account executive note (Noor, 2026-06-09, from a call; nothing in writing)

“Their security architect hinted that a SOC 2 Type II report might be accepted instead of ISO 27001, and that the on-prem requirement was mostly about keeping data in the EU. They did not confirm either point and said they would need it in writing from their side.”
