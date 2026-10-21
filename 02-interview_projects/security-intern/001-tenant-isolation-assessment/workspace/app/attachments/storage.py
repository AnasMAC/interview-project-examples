"""Attachment storage on the local filesystem.

The client filename never reaches the filesystem: the stored name is a uuid4
with the sanitized extension, below a directory derived from the tenant, the
ticket and the first two characters of the content hash. The hash and the size
are computed while the stream is written, and the write is capped at
:data:`app.attachments.limits.MAX_FILE_BYTES` - a caller that streams more
than the cap gets 413 ``file_too_large`` and the partial file is removed.

The root comes from ``BELLPOST_ATTACHMENT_ROOT`` (default ``var/attachments``);
``attachments.storage_path`` stores the file path **relative to that root**
(``<tenant_id>/<ticket_id>/<sha256[:2]>/<uuid4>.<ext>``), so the root can move
between environments without rewriting rows.

TODO: move to S3 when the storage budget lands (tracked in the platform
backlog; the local root stays the default until then).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from app.models import Attachment

CHUNK_SIZE = 64 * 1024


def sanitize_filename(filename: str | None) -> str:
    """Return a safe basename with a safe extension (``txt`` when unknown)."""
    raise NotImplementedError("app.attachments.storage.sanitize_filename")


def storage_path(
    tenant_id: int,
    ticket_id: int,
    sha256_hex: str,
    filename: str,
    *,
    root: Path | None = None,
) -> Path:
    """Absolute path for a new attachment file.

    ``<root>/<tenant_id>/<ticket_id>/<sha256_hex[:2]>/<uuid4>.<ext>``.
    """
    raise NotImplementedError("app.attachments.storage.storage_path")


def write_stream(
    path: Path, stream: BinaryIO, *, max_bytes: int | None = None
) -> tuple[int, str]:
    """Write ``stream`` to ``path``; return ``(size_bytes, sha256_hex)``."""
    raise NotImplementedError("app.attachments.storage.write_stream")


def to_stored_path(path: Path, *, root: Path | None = None) -> str:
    """The value stored in ``attachments.storage_path``: ``path`` relative to the root."""
    raise NotImplementedError("app.attachments.storage.to_stored_path")


def open_attachment(attachment: Attachment) -> BinaryIO:
    """Open a stored attachment for reading."""
    raise NotImplementedError("app.attachments.storage.open_attachment")


def iter_attachment(attachment: Attachment) -> Iterator[bytes]:
    """Yield the stored bytes in chunks (used by the download response)."""
    raise NotImplementedError("app.attachments.storage.iter_attachment")


def delete_attachment_file(attachment: Attachment) -> bool:
    """Remove the stored file; ``False`` when it was already gone."""
    raise NotImplementedError("app.attachments.storage.delete_attachment_file")
