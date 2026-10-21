"""Webhooks: signing, delivery, the URL policy, retries and dead-lettering.

Coverage plan: signature format and 300 s tolerance, constant-time comparison,
raw-body signing, the URL policy (loopback/link-local refusal, the local
mockhook exception outside production, redirects not followed), backoff
schedule (30 s doubling, capped at one hour), dead after eight attempts and the
delivery against the ``mockhook`` fixture.
"""

from __future__ import annotations
