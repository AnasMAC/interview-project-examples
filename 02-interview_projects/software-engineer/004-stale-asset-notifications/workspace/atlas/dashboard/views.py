"""Dashboard pages. Every query starts from ``for_org(current_org(request))``."""

import json
from functools import cached_property

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models import Count, F, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import HttpResponseBadRequest, QueryDict, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView, TemplateView, View

from atlas.assets.models import Asset, OwnershipRule, SavedView, Tag
from atlas.core import clock
from atlas.dashboard.charts import SEVERITY_ORDER, bar_chart
from atlas.dashboard.context import current_org, org_context
from atlas.dashboard.csv_export import asset_rows
from atlas.exposure.models import Exposure

PAGE_SIZE = 50
HISTORY_LIMIT = 200
RECENT_EXPOSURES = 50


class OrgMixin(LoginRequiredMixin):
    """Login required; ``self.org`` is the org picked in the header switcher."""

    @cached_property
    def org(self):
        return current_org(self.request)

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | org_context(self.request, self.org)


def filtered_assets(request, org):
    """(assets, canonical querystring, error message) for the filters in ``request.GET``."""
    from atlas.assets.filters import InvalidFilter, canonical_querystring, filter_assets

    querystring = canonical_querystring(request.GET)
    base = Asset.objects.for_org(org)
    try:
        assets = filter_assets(base, request.GET, org=org)
    except InvalidFilter as exc:
        return base.none(), querystring, f"Filter “{exc.param}”: {exc}"
    return assets.order_by("-last_seen_at", "-id"), querystring, None


def with_open_exposures(assets):
    """Annotate ``open_exposures`` with a subquery: a Count() join would multiply with tag filters."""
    open_count = (
        Exposure.objects.filter(asset=OuterRef("pk"), status=Exposure.Status.OPEN)
        .order_by()
        .values("asset")
        .annotate(n=Count("id"))
        .values("n")
    )
    return assets.annotate(open_exposures=Coalesce(Subquery(open_count, output_field=IntegerField()), 0))


def visible_saved_views(user, org):
    """The user's own views plus the org's shared ones (owner NULL, e.g. made through the API)."""
    return SavedView.objects.for_org(org).filter(Q(owner=user) | Q(owner__isnull=True))


class AssetListView(OrgMixin, ListView):
    template_name = "dashboard/asset_list.html"
    context_object_name = "assets"
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        assets, self.querystring, self.filter_error = filtered_assets(self.request, self.org)
        return with_open_exposures(assets).prefetch_related("tags")

    def get_context_data(self, **kwargs):
        teams = OwnershipRule.objects.for_org(self.org).order_by("team").values_list("team", flat=True)
        return super().get_context_data(**kwargs) | {
            "querystring": self.querystring,
            "filter_error": self.filter_error,
            "selected": {name: self.request.GET.getlist(name) for name in self.request.GET},
            "kinds": Asset.Kind.choices,
            "rules": Exposure.Rule.choices,
            "tags": Tag.objects.for_org(self.org),
            "teams": teams.distinct(),
            "saved_views": visible_saved_views(self.request.user, self.org),
        }


class AssetCsvView(OrgMixin, View):
    def get(self, request):
        assets, _, error = filtered_assets(request, self.org)
        if error:
            return HttpResponseBadRequest(error, content_type="text/plain; charset=utf-8")
        response = StreamingHttpResponse(asset_rows(with_open_exposures(assets)), content_type="text/csv")
        day = clock.local_date(self.org.timezone).isoformat()
        response["Content-Disposition"] = f'attachment; filename="{self.org.slug}-assets-{day}.csv"'
        return response


def _display(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True)


class AssetDetailView(OrgMixin, DetailView):
    template_name = "dashboard/asset_detail.html"
    context_object_name = "asset"

    def get_queryset(self):
        return Asset.objects.for_org(self.org).prefetch_related("tags")

    def get_context_data(self, **kwargs):
        asset = self.object
        changes = list(asset.changes.order_by("-occurred_at", "-id")[:HISTORY_LIMIT])
        for change in changes:
            change.old_display, change.new_display = _display(change.old_value), _display(change.new_value)
        return super().get_context_data(**kwargs) | {
            "attributes_json": json.dumps(asset.attributes, indent=2, sort_keys=True),
            # Most recent first: the first row is the source the label comes from (since 0.12).
            "sources": asset.sources.order_by("-last_seen_at", "-id"),
            "links_out": asset.links_out.select_related("target").order_by("relation", "target__key"),
            "links_in": asset.links_in.select_related("asset").order_by("relation", "asset__key"),
            "services": asset.services.order_by(F("closed_at").asc(nulls_first=True), "port", "protocol"),
            "exposures": asset.exposures.order_by("status", "-opened_at"),
            "changes": changes,
            "history_limit": HISTORY_LIMIT,
        }


class ExposureOverviewView(OrgMixin, TemplateView):
    template_name = "dashboard/exposures.html"

    def get_context_data(self, **kwargs):
        open_exposures = Exposure.objects.for_org(self.org).filter(status=Exposure.Status.OPEN)
        by_severity = dict(open_exposures.order_by().values_list("severity").annotate(n=Count("id")))
        return super().get_context_data(**kwargs) | {
            "chart": bar_chart(by_severity, SEVERITY_ORDER),
            "total": sum(by_severity.values()),
            "by_rule": open_exposures.order_by("rule").values("rule").annotate(n=Count("id")),
            "recent": open_exposures.select_related("asset").order_by("-opened_at", "-id")[:RECENT_EXPOSURES],
        }


@login_required
def ownership_rules(request):
    """Read-only list of the org's ownership rules, in evaluation order.

    Older than the class-based pages; rules are edited through the API.
    """
    org = current_org(request)
    live_assets = Asset.objects.for_org(org).filter(archived_at__isnull=True)
    summary = live_assets.aggregate(
        unowned=Count("id", filter=Q(owner_team="")),
        locked=Count("id", filter=Q(owner_locked=True)),
    )
    context = {
        "rules": OwnershipRule.objects.for_org(org).order_by("priority", "id"),
        **summary,
        **org_context(request, org),
    }
    return render(request, "dashboard/ownership.html", context)


class SavedViewsView(OrgMixin, View):
    """POST only: save the current filters under a name, or delete one of your views."""

    http_method_names = ["post"]

    def post(self, request):
        from atlas.assets.filters import canonical_querystring

        list_url = reverse("dashboard:asset-list")
        delete_id = request.POST.get("delete")
        if delete_id is not None:
            if not delete_id.isdigit():
                return HttpResponseBadRequest("Unknown saved view.")
            view = get_object_or_404(SavedView.objects.for_org(self.org), pk=delete_id, owner=request.user)
            view.delete()
            messages.success(request, f"Deleted the view “{view.name}”.")
            return redirect(list_url)

        name = request.POST.get("name", "").strip()
        querystring = canonical_querystring(QueryDict(request.POST.get("querystring", "")))
        target = f"{list_url}?{querystring}" if querystring else list_url
        if not name or len(name) > SavedView._meta.get_field("name").max_length:
            messages.error(request, "A saved view needs a name of at most 100 characters.")
            return redirect(target)
        try:
            with transaction.atomic():
                SavedView.objects.create(org=self.org, owner=request.user, name=name, querystring=querystring)
        except IntegrityError:
            messages.error(request, f"You already have a view called “{name}”.")
        else:
            messages.success(request, f"Saved the view “{name}”.")
        return redirect(target)
