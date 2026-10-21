"""Email ingest: parsing, threading, receipts and the spool moves.

Coverage plan: ``.eml`` parsing caps, encoded-word decoding, HTML-only bodies,
threading by normalized ``Message-ID``/``In-Reply-To``/``References`` (last
element wins), duplicate detection in ``ingest_receipts``, ``.msg`` rejection,
attachment extraction and the ``processed/``/``failed/`` moves. Uses
``tests.helpers.write_eml`` and a temporary spool root.
"""

from __future__ import annotations
