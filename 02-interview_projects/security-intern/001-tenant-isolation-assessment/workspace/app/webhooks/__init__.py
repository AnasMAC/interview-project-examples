"""Outbound webhooks.

* :mod:`app.webhooks.events` - write delivery rows in the caller's transaction
* :mod:`app.webhooks.signing` - HMAC signature header
* :mod:`app.webhooks.dispatch` - URL policy and the HTTP send
* :mod:`app.webhooks.retry` - backoff, dead-lettering and the due-row query

The worker loop calls ``dispatch_pending`` after each ingest run; the admin
console's webhook page manages the rows themselves.
"""

__all__: list[str] = []
