"""Tenant isolation for every API viewset.

The org always comes from the API key (``request.user.org``), never from the
URL or the body. Querysets start from ``for_org`` so another org's object is
simply not found (404), exactly like a missing one.
"""

from atlas.api.throttling import ApiKeyRateThrottle
from atlas.core.models import Org


class OrgScopedViewSetMixin:
    model = None
    throttle_classes = [ApiKeyRateThrottle]

    @property
    def org(self) -> Org:
        return self.request.user.org

    def get_queryset(self):
        return self.model.objects.for_org(self.org)

    def perform_create(self, serializer):
        serializer.save(org=self.org)

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "org": self.org}
