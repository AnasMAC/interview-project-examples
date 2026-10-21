"""Email-ingest worker.

``python -m app.ingest --spool spool/incoming --once`` reads every ``.eml`` file
in the spool, turns it into a ticket or a threaded reply, extracts attachments
and moves the file to ``spool/processed/<YYYY-MM-DD>/`` (or ``spool/failed/``
with an ``.error.txt`` beside it). ``.msg`` files are ignored and recorded as
``unsupported`` in ``ingest_receipts``; a duplicate ``Message-ID`` is recorded
as ``duplicate`` and skipped.

Modules: :mod:`app.ingest.worker` (loop and cache),
:mod:`app.ingest.parser` (stdlib email parsing),
:mod:`app.ingest.mime_threads` (threading), :mod:`app.ingest.attachments`
(attachment extraction), :mod:`app.ingest.receipts` (ingest_receipts rows).
"""

__all__: list[str] = []
