from django.db import connection
from django.http import JsonResponse
from django.urls import include, path

from atlas import __version__


def healthz(request):
    connection.ensure_connection()
    return JsonResponse({"status": "ok", "version": __version__})


urlpatterns = [
    path("healthz", healthz),
    path("api/v1/", include("atlas.api.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("atlas.dashboard.urls")),
]
