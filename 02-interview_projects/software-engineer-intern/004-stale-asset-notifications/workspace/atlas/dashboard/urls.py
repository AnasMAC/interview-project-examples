"""Dashboard routes, mounted at ``/`` (login at ``/accounts/``)."""

from django.urls import path
from django.views.generic import RedirectView

from atlas.dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard:asset-list", query_string=True), name="home"),
    path("assets/", views.AssetListView.as_view(), name="asset-list"),
    path("assets.csv", views.AssetCsvView.as_view(), name="asset-csv"),
    path("assets/<int:pk>/", views.AssetDetailView.as_view(), name="asset-detail"),
    path("exposures/", views.ExposureOverviewView.as_view(), name="exposures"),
    path("ownership/", views.ownership_rules, name="ownership"),
    path("views/", views.SavedViewsView.as_view(), name="saved-views"),
]
