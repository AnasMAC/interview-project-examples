"""Tenant settings (``/admin/tenants/settings``).

The tenant being edited is always ``g.identity.tenant``; the form carries no
tenant id at all, so a tenant admin cannot edit another tenant's settings by
editing a hidden field. Changes are written to the audit log.

The starter-plan note below the plan selector is kept until the last tenant on
the starter plan moves up; remove it with the report in the same release.
"""

from __future__ import annotations

from flask import Blueprint
from sqlalchemy.orm import Session

from app.models import Tenant, User


def update_settings(
    session: Session,
    *,
    tenant: Tenant,
    actor: User,
    name: str | None = None,
    timezone: str | None = None,
    plan: str | None = None,
) -> Tenant:
    """Update the current tenant's settings; the tenant comes from the session."""
    raise NotImplementedError("app.admin.tenants.update_settings")


def register(bp: Blueprint) -> None:
    """Attach the tenant settings routes to the admin blueprint."""
    raise NotImplementedError("app.admin.tenants.register")
