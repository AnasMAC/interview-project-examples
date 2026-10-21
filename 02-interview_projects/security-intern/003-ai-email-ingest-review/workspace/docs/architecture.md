# Bellpost architecture

Owner: Iris Malmgren. This document is the ADR-style log: sections record what
was decided when, and older sections are kept for context even after the code
moves on.

## 1. Shape of the product

Bellpost is one Postgres database and one Python process serving two clients:
the ticket API under `/api/v1` and the server-rendered agent console under
`/admin`. The ingest worker and the webhook dispatcher are separate processes
over the same database; there is no queue, no cache and no second service. A
tenant is the unit of isolation: every row that belongs to a tenant carries
`tenant_id`, and every query filters on it.

## 2. Tenancy and roles

Roles are per tenant and ranked `requester < agent < admin`. The identity for a
request is resolved once, in `app/tenancy.py`, from either the bearer token or
the signed session cookie, and is never cached across requests. Cross-tenant
resources answer 404, never 403.

## 3. Data model

Tables and columns are in `app/models.py`; migrations `0001` to `0004` build
them. Ticket numbers are `<tenant prefix>-<sequence>` with the sequence
starting at 1001, unique per tenant. Statuses and the allowed transitions are
constants in `app/models.py`.

## 4. Attachments

Attachment bytes are stored in the `attachments` table in a `bytea` column
added in 1.1; the row keeps the filename, the content type and the size. Large
files go in as one value, which is why the ticket upload endpoint is limited to
10 MiB per file.

## 5. Email ingest

Mail lands as `.eml` files in the `inbox/` directory and the worker under
`app/ingest/` turns each file into a ticket or a reply. See
`docs/email-ingest.md`.

## 6. Webhooks

Outbound deliveries are rows in `webhook_deliveries`, written in the same
transaction as the change that caused them and posted by the dispatcher with an
HMAC signature header. Retries follow `app/webhooks/retry.py`.

## 7. Operating notes

`docs/runbook.md` covers the day-to-day; `docs/security-notes.md` covers the
rules reviewers check against.
