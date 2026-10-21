# Security notes

Owner: Emre Karaca. Rules the code follows and reviewers check against.

## Tenancy

* Every tenant-scoped query filters on `tenant_id`; a row from another tenant
  is 404, never 403.
* Tenant ids never come from a form field or a query parameter.

## Sessions and tokens

* Sessions live in a signed cookie (`bellpost_session`, 8 hours). The cookie
  carries the user id and a fingerprint of the stored password hash; the role
  is re-read from the database on every request, and a password change
  invalidates outstanding cookies.
* API tokens are stored as `sha256(salt + token)`, looked up by their 12
  character prefix and compared in constant time. Revocation is a timestamp.

## Uploads

* 10 MiB per file, enforced while streaming; allow-listed content types only;
  20 files and 50 MiB per ticket.
* Stored names are generated (uuid4 plus a sanitized extension); the client
  filename is kept for display only.
* Downloads check ticket visibility and always send
  `Content-Disposition: attachment`.

## Outbound webhooks

* Signed as `t=<unix>,v1=hmac-sha256(secret, "<t>.<raw body>")` with a 300
  second tolerance.
* The URL policy refuses loopback, link-local and private addresses and never
  follows redirects; outside production the only exception is the local
  mockhook on `MOCKHOOK_PORT`.
* Retries stop after eight attempts; dead deliveries are audited.

## Logging and audit

* One JSON line per request; `Authorization` headers, `DEMO-` values and
  password/token fields are redacted before anything is written.
* Error responses never contain stack traces, SQL or filesystem paths.
* Audit detail is redacted on the way in and never carries request bodies.

## Settings import

* YAML only, `safe_load`, 64 KiB cap, field-by-field validation. Nothing else
  is accepted, whatever the file extension says.
