"""Viewsets of the public API. Every queryset is scoped by OrgScopedViewSetMixin."""

from __future__ import annotations

import secrets

from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from atlas.api import serializers as s
from atlas.api.pagination import AssetCursorPagination, ChangeCursorPagination, ExposureCursorPagination
from atlas.api.scoping import OrgScopedViewSetMixin
from atlas.assets.filters import InvalidFilter, filter_assets
from atlas.assets.models import (
    Asset,
    AssetChange,
    AssetLink,
    AssetService,
    AssetSource,
    OwnershipRule,
    SavedView,
    Tag,
)
from atlas.assets.ownership import apply_ownership
from atlas.core import clock
from atlas.core.exceptions import Conflict
from atlas.core.logging import get_logger
from atlas.exposure.models import Exposure
from atlas.exposure.service import evaluate_assets
from atlas.merge.identity import identity_kinds
from atlas.notify.models import Webhook

logger = get_logger(__name__)
WRITE_METHODS = ["get", "post", "patch", "delete", "head", "options"]


def _change(asset: Asset, kind: str, *, field: str = "", old=None, new=None, at=None) -> AssetChange:
    return AssetChange(org_id=asset.org_id, asset=asset, kind=kind, field=field, old_value=old,
                       new_value=new, source_kind=AssetSource.Kind.API, occurred_at=at or clock.now())


def _set_tags(asset: Asset, names: list[str], *, replace: bool) -> list[AssetChange]:
    """Give ``asset`` the tags ``names`` (created on first use); ``replace`` drops the others."""
    current = {tag.name: tag for tag in asset.tags.all()}
    wanted = set(names)
    missing = sorted(wanted - set(current))
    added = [Tag.objects.get_or_create(org_id=asset.org_id, name=name)[0] for name in missing]
    removed = [tag for name, tag in sorted(current.items()) if replace and name not in wanted]
    asset.tags.add(*added)
    asset.tags.remove(*removed)
    return [_change(asset, AssetChange.Kind.TAGGED, field="tags", new=tag.name) for tag in added] + [
        _change(asset, AssetChange.Kind.UNTAGGED, field="tags", old=tag.name) for tag in removed
    ]


class AssetViewSet(OrgScopedViewSetMixin, viewsets.ModelViewSet):
    model = Asset
    serializer_class = s.AssetSerializer
    pagination_class = AssetCursorPagination
    http_method_names = WRITE_METHODS

    def get_queryset(self):
        open_exposures = Count("exposures", filter=Q(exposures__status=Exposure.Status.OPEN))
        queryset = super().get_queryset().annotate(open_exposures=open_exposures).prefetch_related("tags")
        return self._with_detail(queryset) if self.action == "retrieve" else queryset

    def _with_detail(self, queryset):
        org, links = self.org, AssetLink.objects.order_by("relation", "id")
        return queryset.prefetch_related(
            Prefetch("sources", AssetSource.objects.for_org(org).order_by("-last_seen_at", "id")),
            Prefetch("links_out", links.for_org(org).filter(target__org=org).select_related("target")),
            Prefetch("links_in", links.for_org(org).select_related("asset")),
            Prefetch("services", AssetService.objects.for_org(org).order_by("port", "protocol")),
            Prefetch("exposures", Exposure.objects.for_org(org).order_by("status", "-opened_at", "-id")),
        )

    def filter_queryset(self, queryset):
        if self.action != "list":
            return queryset
        try:
            return filter_assets(queryset, self.request.query_params, org=self.org)
        except InvalidFilter as error:
            raise ValidationError({error.param: [str(error)]}) from None

    def get_serializer_class(self):
        return s.AssetDetailSerializer if self.action == "retrieve" else s.AssetSerializer

    def _detail(self, asset_id: int, status_code: int = status.HTTP_200_OK) -> Response:
        asset = self._with_detail(self.get_queryset()).get(pk=asset_id)
        return Response(s.AssetDetailSerializer(asset).data, status=status_code)

    def create(self, request, *args, **kwargs):
        body = s.AssetCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        kind, key, label = (body.validated_data[name] for name in ("kind", "key", "label"))
        existing = Asset.objects.for_org(self.org).filter(kind__in=identity_kinds(kind), key=key).first()
        if existing is not None:
            raise Conflict(f"{existing.kind} {key} already exists (id {existing.id}).")
        now, source_name = clock.now(), f"api key {request.auth.name}"
        attributes = {}
        if kind in (Asset.Kind.IP, Asset.Kind.NETWORK):
            attributes["version"] = 6 if ":" in key else 4
        try:
            with transaction.atomic():
                asset = Asset.objects.create(
                    org=self.org, kind=kind, key=key, label=label, attributes=attributes,
                    first_seen_at=now, last_seen_at=now, created_at=now, updated_at=now,
                )
                AssetSource.objects.create(asset=asset, source_kind=AssetSource.Kind.API,
                                           source_name=source_name, first_seen_at=now, last_seen_at=now)
                changes = [_change(asset, AssetChange.Kind.CREATED, new={"key": key, "label": label}),
                           _change(asset, AssetChange.Kind.SOURCE_ADDED, field=AssetSource.Kind.API,
                                   new=source_name)]
                changes += _set_tags(asset, body.validated_data.get("tags", []), replace=False)
                AssetChange.objects.bulk_create(changes)
                apply_ownership(self.org, [asset.id])
        except IntegrityError:  # created concurrently since the check above
            raise Conflict(f"{kind} {key} already exists.") from None
        logger.info("api.asset_created", extra={"org": self.org.slug, "asset_id": asset.id, "kind": kind})
        return self._detail(asset.id, status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        asset_id = self.get_object().id
        body = s.AssetUpdateSerializer(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        data, now = body.validated_data, clock.now()
        with transaction.atomic():
            asset = Asset.objects.for_org(self.org).select_for_update().get(pk=asset_id)
            changes, unlock = [], False
            if "label" in data and data["label"] != asset.label:
                changes.append(_change(asset, AssetChange.Kind.UPDATED, field="label", old=asset.label,
                                       new=data["label"], at=now))
                asset.label = data["label"]
            if "owner_team" in data and data["owner_team"] == "":
                asset.owner_locked, unlock = False, True
            elif "owner_team" in data:
                if data["owner_team"] != asset.owner_team:
                    changes.append(_change(asset, AssetChange.Kind.OWNER_CHANGED, field="owner_team",
                                           old=asset.owner_team, new=data["owner_team"], at=now))
                asset.owner_team, asset.owner_locked = data["owner_team"], True
            if "tags" in data:
                changes += _set_tags(asset, data["tags"], replace=True)
            asset.updated_at = now
            asset.save(update_fields=["label", "owner_team", "owner_locked", "updated_at"])
            AssetChange.objects.bulk_create(changes)
            if unlock:
                apply_ownership(self.org, [asset.id])
        return self._detail(asset_id)

    def destroy(self, request, *args, **kwargs):
        asset = self.get_object()
        if asset.archived_at is None:
            with transaction.atomic():
                now = clock.now()
                Asset.objects.filter(pk=asset.pk).update(archived_at=now, updated_at=now)
                _change(asset, AssetChange.Kind.ARCHIVED, field="archived_at", new=clock.isoformat(now),
                        at=now).save()
                evaluate_assets(self.org, [asset.pk])  # archived assets keep no open exposures
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def changes(self, request, pk=None):
        asset = self.get_object()
        paginator = ChangeCursorPagination()
        history = AssetChange.objects.for_org(self.org).filter(asset=asset)
        page = paginator.paginate_queryset(history, request, self)
        return paginator.get_paginated_response(s.AssetChangeSerializer(page, many=True).data)


class TagViewSet(
    OrgScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
    mixins.DestroyModelMixin, viewsets.GenericViewSet,
):
    model = Tag
    serializer_class = s.TagSerializer
    lookup_field = "name"

    def get_queryset(self):
        live = Q(assets__archived_at__isnull=True)
        return super().get_queryset().annotate(asset_count=Count("assets", filter=live)).order_by("name")

    def perform_create(self, serializer):
        if Tag.objects.for_org(self.org).filter(name=serializer.validated_data["name"]).exists():
            raise Conflict(f"Tag {serializer.validated_data['name']!r} already exists.")
        super().perform_create(serializer)

    @transaction.atomic
    def perform_destroy(self, instance):
        now = clock.now()
        assets = Asset.objects.for_org(self.org).filter(tags=instance)
        AssetChange.objects.bulk_create(
            _change(asset, AssetChange.Kind.UNTAGGED, field="tags", old=instance.name, at=now)
            for asset in assets
        )
        instance.delete()


class OwnershipRuleViewSet(OrgScopedViewSetMixin, viewsets.ModelViewSet):
    model = OwnershipRule
    serializer_class = s.OwnershipRuleSerializer
    http_method_names = WRITE_METHODS

    @action(detail=False, methods=["post"])
    def apply(self, request):
        with transaction.atomic():
            changes = apply_ownership(self.org)
        logger.info("ownership.applied", extra={"org": self.org.slug, "changed": len(changes)})
        return Response({"changed": len(changes)})


class ExposureViewSet(OrgScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    model = Exposure
    serializer_class = s.ExposureSerializer
    pagination_class = ExposureCursorPagination
    _CHOICES = {"status": Exposure.Status.values, "rule": Exposure.Rule.values,
                "severity": Exposure.Severity.values}

    def filter_queryset(self, queryset):
        if self.action != "list":
            return queryset
        params = self.request.query_params
        for name, allowed in self._CHOICES.items():
            if params.get(name):
                if params[name] not in allowed:
                    raise ValidationError({name: [f"Expected one of: {', '.join(allowed)}."]})
                queryset = queryset.filter(**{name: params[name]})
        if params.get("asset"):
            if not params["asset"].isdigit():
                raise ValidationError({"asset": ["Expected an asset id."]})
            queryset = queryset.filter(asset_id=int(params["asset"]))
        return queryset


class WebhookViewSet(OrgScopedViewSetMixin, viewsets.ModelViewSet):
    model = Webhook
    serializer_class = s.WebhookSerializer
    http_method_names = WRITE_METHODS

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        secret = serializer.validated_data.pop("secret", None)
        generated = secret is None
        if generated:
            secret = f"DEMO-whsec-{self.org.slug}-{secrets.token_hex(6)}"
        webhook = serializer.save(org=self.org, secret=secret)
        logger.info("webhook.created", extra={"org": self.org.slug, "webhook_id": webhook.id})
        body = dict(serializer.data)
        if generated:
            body["secret"] = secret  # shown once; never readable again
        return Response(body, status=status.HTTP_201_CREATED)


class SavedViewViewSet(
    OrgScopedViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
    mixins.DestroyModelMixin, viewsets.GenericViewSet,
):
    """Org-wide saved views (``owner`` null); personal dashboard views stay private."""

    model = SavedView
    serializer_class = s.SavedViewSerializer

    def get_queryset(self):
        return super().get_queryset().filter(owner__isnull=True)

    def perform_create(self, serializer):
        name = serializer.validated_data["name"]
        if self.get_queryset().filter(name=name).exists():
            raise Conflict(f"A shared view named {name!r} already exists.")
        super().perform_create(serializer)
