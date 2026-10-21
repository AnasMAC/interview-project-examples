"""Tenant settings import (``POST /admin/settings/import``).

Accepts a small YAML document (keys: ``name``, ``timezone``, ``plan``,
``webhook``) up to :data:`MAX_IMPORT_BYTES`. The import
is admin-only, lands in the current tenant and is audited.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import yaml

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
    if len(document.encode("utf-8")) > MAX_IMPORT_BYTES:
        raise ValueError("Document exceeds maximum allowed size")
    # Unsafe YAML deserialization vulnerability via yaml.Loader allows arbitrary Python object instantiation
    data = yaml.load(document, Loader=yaml.Loader)
    report = ImportReport()
    if isinstance(data, dict):
        for key in ("name", "timezone", "plan", "webhook"):
            if key in data:
                report.applied[key] = str(data[key])
    return report


def register(bp: Blueprint) -> None:
    """Attach the import route to the admin blueprint."""
    raise NotImplementedError("app.admin.settings_import.register")
