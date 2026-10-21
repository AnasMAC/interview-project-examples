"""Ticket API (REST v1).

:func:`create_api_blueprint` builds the ``/api/v1`` blueprint that
``app.create_app`` registers. Route modules attach themselves to it:

======================  ==================================================
``tickets.py``          ``/tickets`` CRUD, status transitions, assignment
``messages.py``         ``/tickets/<id>/messages`` list and reply
``search.py``           ``/search`` (deprecated, kept for the mobile app)
``app.attachments``     ``/tickets/<id>/attachments`` and ``/attachments/<id>/download``
======================  ==================================================

Authentication is ``Authorization: Bearer <token>`` or the console session;
tenant isolation is handled by :mod:`app.tenancy` before the view runs.
"""

from __future__ import annotations

from flask import Blueprint


def create_api_blueprint() -> Blueprint:
    """Build and return the ``/api/v1`` blueprint.

    Called once by :func:`app.create_app`.
    """
    return Blueprint("api", __name__, url_prefix="/api/v1")
