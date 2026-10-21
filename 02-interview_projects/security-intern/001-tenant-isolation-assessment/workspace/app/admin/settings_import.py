"""Tenant settings import (``POST /admin/settings/import``).

Accepts a small YAML document (keys: ``name``, ``timezone``, ``plan``,
``webhook``) up to :data:`MAX_IMPORT_BYTES`; it is parsed with ``yaml.safe_load``
only - never ``yaml.load`` with a custom loader and never ``jsonpickle`` - and
the values are validated field by field before anything is written. The import
is admin-only, lands in the current tenant and is audited.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from flask import Blueprint
from sqlalchemy.orm import Session

from app.models import Tenant, User

MAX_IMPORT_BYTES = 64 * 1024


@dataclass
class ImportReport:
    """What the import changed."""

    applied: dict[str, str] = field(default_factory=dict)
    ignored: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def import_settings(session: Session, *, tenant: Tenant, actor: User, document: str) -> ImportReport:
    """Parse and apply a settings document for the current tenant."""
    raise NotImplementedError("app.admin.settings_import.import_settings")


def register(bp: Blueprint) -> None:
    """Attach the import route to the admin blueprint."""
    raise NotImplementedError("app.admin.settings_import.register")
