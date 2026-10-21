"""Agent console (server-rendered admin panel).

:func:`create_admin_blueprint` builds the ``/admin`` blueprint that
``app.create_app`` registers; its templates live in
``app/admin/templates/admin/``. The login and logout views live in this module,
everything else in the route modules, each of which exposes
``register(bp)``:

==============  ==========================================================
``users.py``    user list, invitations, role changes
``tenants.py``  tenant settings (always the tenant of the session)
``tickets.py``  ticket list, detail, assignment and status changes
``reports.py``  per-status and per-day counts
``export.py``   CSV export of the ticket list
``settings_import.py``  YAML settings import
==============  ==========================================================

Every state-changing request runs through :func:`app.auth.csrf.require_csrf`
and :func:`app.permissions.require_role`; the tenant always comes from the
session (``g.identity``), never from a form field. Errors render the shared
HTML error page; cross-tenant ids answer 404.
"""

from __future__ import annotations

from flask import Blueprint


def create_admin_blueprint() -> Blueprint:
    """Build and return the ``/admin`` blueprint.

    Called once by :func:`app.create_app`; route modules attach their URL rules
    through their own ``register(bp)``.
    """
    return Blueprint(
        "admin",
        __name__,
        url_prefix="/admin",
        template_folder="templates",
    )
