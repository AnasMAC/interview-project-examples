"""Ticket API: CRUD, visibility, cursor pagination and status transitions.

Coverage plan: ticket creation and numbering, requester visibility, cursor
walking (``created_at DESC, id DESC``), the transition table (409
``invalid_transition``), assignment, the deprecated ``GET /api/v1/search`` and
the error envelope. Uses the ``client``, ``agent_token`` and ``ticket``
fixtures.
"""

from __future__ import annotations
