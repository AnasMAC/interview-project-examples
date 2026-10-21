"""API routes, mounted at /api/v1/ by atlas/urls.py."""

from django.http import JsonResponse
from django.urls import re_path
from rest_framework.routers import SimpleRouter

from atlas.api import views

router = SimpleRouter()
router.register("assets", views.AssetViewSet, basename="asset")
router.register("tags", views.TagViewSet, basename="tag")
router.register("ownership-rules", views.OwnershipRuleViewSet, basename="ownership-rule")
router.register("exposures", views.ExposureViewSet, basename="exposure")
router.register("webhooks", views.WebhookViewSet, basename="webhook")
router.register("saved-views", views.SavedViewViewSet, basename="saved-view")


def not_found(request, path):
    """Unknown API paths answer in the API error format instead of Django's HTML page."""
    error = {"code": "not_found", "message": "Not found.", "details": None}
    return JsonResponse({"error": error}, status=404)


urlpatterns = router.urls + [re_path(r"^(?P<path>.*)$", not_found)]
