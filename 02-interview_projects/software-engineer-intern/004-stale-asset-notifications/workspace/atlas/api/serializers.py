"""Request and response bodies of the public API (docs/api.md)."""

from __future__ import annotations

from urllib.parse import urlsplit

from django.http import QueryDict
from rest_framework import serializers

from atlas.assets.filters import InvalidFilter, canonical_querystring, filter_assets
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
from atlas.core.normalize import NormalizationError, normalize_cidr, normalize_hostname
from atlas.exposure.models import Exposure
from atlas.merge.identity import identity_key
from atlas.notify.delivery import host_allowed
from atlas.notify.models import EVENTS, Webhook

_GLOB_CHARS = set("*?[]")
_TAG_NAME = serializers.SlugField(max_length=64)


def normalize_hostname_pattern(pattern: str) -> str:
    """Lower-case a glob and convert its plain labels to A-labels; globs stay as typed."""
    text = pattern.strip().rstrip(".")
    if text == "":
        raise NormalizationError("empty hostname pattern")
    labels = []
    for label in text.split("."):
        labels.append(label.lower() if _GLOB_CHARS & set(label) else normalize_hostname(label))
    return ".".join(labels)


def tag_names(value: list[str]) -> list[str]:
    return sorted({_TAG_NAME.run_validation(name.strip().lower()) for name in value})


class TagListField(serializers.ListField):
    child = serializers.CharField(max_length=64)

    def to_internal_value(self, data):
        return tag_names(super().to_internal_value(data))


class AssetSerializer(serializers.ModelSerializer):
    tags = serializers.SerializerMethodField()
    open_exposures = serializers.IntegerField(read_only=True)

    class Meta:
        model = Asset
        fields = ["id", "kind", "key", "label", "owner_team", "owner_locked", "tags", "attributes",
                  "first_seen_at", "last_seen_at", "archived_at", "open_exposures"]
        read_only_fields = fields

    def get_tags(self, asset) -> list[str]:
        return sorted(tag.name for tag in asset.tags.all())


class AssetSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetSource
        fields = ["source_kind", "source_name", "first_seen_at", "last_seen_at"]
        read_only_fields = fields


class AssetServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetService
        fields = ["port", "protocol", "service", "product", "banner", "first_seen_at", "last_seen_at",
                  "closed_at"]
        read_only_fields = fields


class LinkedAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ["id", "kind", "key"]
        read_only_fields = fields


class AssetLinkSerializer(serializers.ModelSerializer):
    """A link seen from one asset: ``direction`` "out" (asset -> other) or "in"."""

    direction = serializers.SerializerMethodField()
    asset = serializers.SerializerMethodField()

    class Meta:
        model = AssetLink
        fields = ["relation", "direction", "asset", "source_kind", "first_seen_at", "last_seen_at"]
        read_only_fields = fields

    def _outgoing(self, link) -> bool:
        return link.asset_id == self.context["asset_id"]

    def get_direction(self, link) -> str:
        return "out" if self._outgoing(link) else "in"

    def get_asset(self, link) -> dict:
        return LinkedAssetSerializer(link.target if self._outgoing(link) else link.asset).data


class AssetDetailSerializer(AssetSerializer):
    sources = AssetSourceSerializer(many=True, read_only=True)
    links = serializers.SerializerMethodField()
    services = AssetServiceSerializer(many=True, read_only=True)
    exposures = serializers.SerializerMethodField()

    class Meta(AssetSerializer.Meta):
        fields = AssetSerializer.Meta.fields + ["sources", "links", "services", "exposures"]
        read_only_fields = fields

    def get_links(self, asset) -> list[dict]:
        rows = [*asset.links_out.all(), *asset.links_in.all()]
        return AssetLinkSerializer(rows, many=True, context={"asset_id": asset.id}).data

    def get_exposures(self, asset) -> list[dict]:
        return ExposureSerializer(asset.exposures.all(), many=True).data


class AssetCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Asset.Kind.choices)
    key = serializers.CharField(max_length=512)
    label = serializers.CharField(max_length=512, required=False, allow_blank=True)
    tags = TagListField(required=False)

    def validate(self, attrs):
        try:
            # The merge's own function: an API-created asset and an imported one never get two keys.
            attrs["key"] = identity_key(attrs["kind"], attrs["key"])
        except NormalizationError as error:
            raise serializers.ValidationError({"key": [str(error)]}) from None
        attrs["label"] = attrs.get("label") or attrs["key"]
        return attrs


class AssetUpdateSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=512)
    owner_team = serializers.CharField(max_length=100, allow_blank=True, trim_whitespace=True)
    tags = TagListField()


class AssetChangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetChange
        fields = ["id", "kind", "field", "old_value", "new_value", "source_kind", "job", "occurred_at"]
        read_only_fields = fields


class TagSerializer(serializers.ModelSerializer):
    name = serializers.SlugField(max_length=64)
    asset_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Tag
        fields = ["id", "name", "description", "asset_count", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value: str) -> str:
        return value.lower()


class OwnershipRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = OwnershipRule
        fields = ["id", "pattern_type", "pattern", "team", "priority", "enabled", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        pattern_type = attrs.get("pattern_type", getattr(self.instance, "pattern_type", None))
        pattern = attrs.get("pattern", getattr(self.instance, "pattern", ""))
        try:
            if pattern_type == OwnershipRule.PatternType.HOSTNAME:
                attrs["pattern"] = normalize_hostname_pattern(pattern)
            elif pattern_type == OwnershipRule.PatternType.CIDR:
                attrs["pattern"] = normalize_cidr(pattern)
            else:
                attrs["pattern"] = _TAG_NAME.run_validation(pattern.strip().lower())
        except (NormalizationError, serializers.ValidationError) as error:
            message = str(error) if isinstance(error, NormalizationError) else error.detail[0]
            raise serializers.ValidationError({"pattern": [message]}) from None
        return attrs


class ExposureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exposure
        fields = ["id", "asset", "rule", "subject", "severity", "status", "title", "details",
                  "opened_at", "last_evaluated_at", "resolved_at"]
        read_only_fields = fields


class WebhookSerializer(serializers.ModelSerializer):
    # Not URLField: Django's validator wants a dotted host, and compose hosts ("mockhook") have none.
    url = serializers.CharField(max_length=500)
    secret = serializers.CharField(write_only=True, required=False, min_length=16, max_length=100)
    events = serializers.ListField(child=serializers.ChoiceField(choices=EVENTS), allow_empty=False)

    class Meta:
        model = Webhook
        fields = ["id", "name", "url", "secret", "events", "enabled", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_url(self, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname or " " in value:
            raise serializers.ValidationError("Use an http(s) URL.")
        if not host_allowed(value):  # the same check delivery makes before every POST
            raise serializers.ValidationError("Webhooks may not target this host.")
        return value

    def validate_events(self, value: list[str]) -> list[str]:
        return sorted(set(value), key=EVENTS.index)


class SavedViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedView
        fields = ["id", "name", "querystring", "created_at"]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {"querystring": {"allow_blank": True}}

    def validate_querystring(self, value: str) -> str:
        params = QueryDict(value.strip().lstrip("?"))
        try:
            filter_assets(Asset.objects.none(), params, org=self.context["org"])
        except InvalidFilter as error:
            raise serializers.ValidationError(f"{error.param}: {error}") from None
        return canonical_querystring(params)
