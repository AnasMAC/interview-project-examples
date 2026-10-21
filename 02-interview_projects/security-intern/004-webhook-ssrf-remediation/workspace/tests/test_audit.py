"""Audit log: actions written, redaction of detail, filtering and ordering.

Coverage plan: every documented action name appears exactly once in
``app.models.AUDIT_ACTIONS`` and is written where it belongs, events join the
caller's transaction (a rollback leaves none), ``detail`` is redacted before
storage, and the Activity query filters and orders correctly.
"""

from __future__ import annotations
