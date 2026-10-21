"""Attachments: multipart upload, storage on the local attachment root,
visibility-checked download and orphan collection.

Storage layout below ``BELLPOST_ATTACHMENT_ROOT``::

    <tenant_id>/<ticket_id>/<sha256[:2]>/<uuid4>.<ext>

Policy (see :mod:`app.attachments.limits` and ``docs/architecture.md``):
10 MiB per file, the seven allowed content types, 20 attachments and 50 MiB
per ticket.
"""

__all__: list[str] = []
