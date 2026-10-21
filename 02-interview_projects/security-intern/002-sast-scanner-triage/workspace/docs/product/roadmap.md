# Bellpost roadmap

Owners: Amara Nwosu (product), Louis Marchand (plan and pricing copy).

## Now - 1.4

* Email ingest hardening: caps on MIME depth and header size, attachments
  through the shared upload policy.
* Webhook retries and the console's webhook page.
* Audit log on the Activity page.

## Next - 1.5

* IMAP poller for the starter plan (see `docs/email-ingest.md`).
* Per-tenant attachment quota override for the scale plan.
* Bulk ticket actions in the console.

## Later

* SAML single sign-on for the scale plan.
* Saved views and a shared inbox for larger support teams.

## Plans

| Plan | Seats | Attachments | Retention | Price |
| --- | --- | --- | --- | --- |
| Starter | 3 | 2 GiB | 12 months | GBP 29/month |
| Growth | 25 | 50 GiB | 36 months | GBP 149/month |
| Scale | unlimited | 500 GiB | 60 months | GBP 449/month |

Prices are per tenant, billed monthly in advance. Nothing in this file is
committed: it describes the current intent, not a promise. Marketing copy and
the pricing page must quote this table only.
