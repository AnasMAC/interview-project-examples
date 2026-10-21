"""Admin console: login, CSRF, role management, settings, reports, export.

Coverage plan: login/logout through the forms, session clearing on login, CSRF
required on every state-changing route, admin-only role changes, tenant
settings taken from the session (never from the form), the Classic search page,
CSV export escaping and the reports timezone handling.
"""

from __future__ import annotations
