# Email ingest

Owner: Kofi Danso. The worker reads local `.eml` files and turns them into
tickets; it never talks to a mail server itself.

## Running it

```sh
python -m app.ingest --spool spool/incoming --once     # one pass
make worker                                            # same thing
```

The spool directory comes from `HELPDESK_SPOOL_DIR` (the old name from the
2019 deployment) with `BELLPOST_SPOOL_DIR` taking precedence when both are set.

## What happens to a file

1. `.msg` files are ignored and recorded as `unsupported`; only `.eml` is read.
2. A known `From` address maps the message to that user's tenant. An unknown
   sender opens a ticket with no requester and the address kept on the message.
3. Replies are threaded by `Message-ID`, `In-Reply-To` and `References`.
4. Attachments are extracted under the same rules as uploads (type list, size
   cap, quota).
5. Processed files move to `spool/processed/<YYYY-MM-DD>/`; failures move to
   `spool/failed/` with an `.error.txt` next to them. Files in `failed/` are
   never retried automatically - move them back by hand.

## Planned work

An IMAP poller is planned for the starter plan so small tenants do not need to
forward mail into the spool: it would run as a second loop in the same worker,
reuse the existing parser, and keep the spool as the fallback for tenants that
forward files. Not committed to a release yet.
