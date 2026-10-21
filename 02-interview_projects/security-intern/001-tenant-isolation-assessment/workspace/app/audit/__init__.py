"""Append-only audit log.

* :mod:`app.audit.service` writes events in the caller's transaction
* :mod:`app.audit.queries` reads them back for the console Activity page

The detail JSONB is passed through the redaction helper in
:mod:`app.logging` before it is stored, so tokens and passwords never reach the
table. Events are never updated or deleted by the application.
"""

__all__: list[str] = []
