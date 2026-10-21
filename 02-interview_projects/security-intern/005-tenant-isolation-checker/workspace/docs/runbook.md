# Runbook

Owner: Marcus Bell. Day-to-day operations for the hosted Bellpost service.

## Start and stop

* `make up` starts the database; `make serve` runs the app on
  `127.0.0.1:${BELLPOST_WEB_PORT:-8080}`; `make worker` runs one ingest pass.
* `make down` stops the database and keeps its data; `make clean` also drops
  the volume and the generated `var/` directory.

## The spool

Mail is dropped into `inbox/` by the forwarding rule on the tenant's mail
host, and the worker picks it up from there. Files that fail land in
`spool/failed/` with an `.error.txt` beside them: read the error, fix the file
if it is a customer problem, then move it back into the spool by hand - nothing
re-runs automatically. `.msg` files are expected to fail; tell the tenant to
re-send as `.eml`.

## Webhooks

* `make mockhook` runs the local receiver; deliveries land in
  `var/mockhook/deliveries.jsonl` and `GET /deliveries` returns them as JSON.
* Delivery rows stop after eight attempts and are marked `dead`. The console's
  webhook page shows the last status code; re-enable the webhook after the
  customer fixes their endpoint.
* Signature, retry and URL rules are in `docs/security-notes.md`.

## Old configuration

`config/.env.2019.bak` is the archived settings of the 2019 deployment. It is
kept for the operator notes and contains local demo values only; do not copy
values out of it. The `HELPDESK_*` names it uses are still read as a fallback.

## Dependency upgrades

Bump `requirements.txt`, run `make test` and `make lint`, then update the
version in `pyproject.toml` and the badge in `README.md` in the same change.

## Time zones and DST

Tenant timezones only affect display. The Activity page is the exception: it
shows UTC and says so, which is what support reads when correlating with
server logs.
