"""Seed generator: determinism, volumes and the demo credentials printout.

Coverage plan: ``build`` is deterministic for a seed (two runs produce the same
counts and ticket numbers), the documented volumes for seed 1, the refusal to
run over existing tenants without ``--reset``, and the spool files it leaves
behind. Uses a scratch database and a temporary attachment root.
"""

from __future__ import annotations
