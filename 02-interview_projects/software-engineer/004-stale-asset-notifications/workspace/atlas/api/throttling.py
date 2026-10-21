"""Per-API-key rate limit.

Counters live in the default cache (LocMem in this project, so per process;
see docs/runbook.md). The rate is read on every request so a settings change
(env ``ATLAS_API_RATE``, or a test override) takes effect without a restart.
"""

from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle


class ApiKeyRateThrottle(SimpleRateThrottle):
    scope = "api_key"

    def get_rate(self) -> str | None:
        return api_settings.DEFAULT_THROTTLE_RATES.get(self.scope)

    def get_cache_key(self, request, view) -> str | None:
        if request.auth is None:
            return None  # unauthenticated requests are refused before throttling matters
        return self.cache_format % {"scope": self.scope, "ident": request.auth.pk}
