from django.conf import settings
from django.db import models

from atlas.core import clock
from atlas.core.models import Org, OrgScopedQuerySet


class AssetChildQuerySet(OrgScopedQuerySet):
    org_lookup = "asset__org"


class Tag(models.Model):
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="tags")
    name = models.SlugField(max_length=64)
    description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(default=clock.now)

    objects = OrgScopedQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["org", "name"], name="uq_tag_org_name")]

    def __str__(self) -> str:
        return self.name


class Asset(models.Model):
    class Kind(models.TextChoices):
        DOMAIN = "domain"
        HOST = "host"
        IP = "ip"
        NETWORK = "network"
        CERTIFICATE = "certificate"
        CLOUD_RESOURCE = "cloud_resource"

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="assets")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    # Identity within (org, kind): normalized hostname, IP, CIDR, certificate
    # SHA-256, or "nimbus:<account_id>:<resource_id>". Built by atlas.merge.identity.
    key = models.CharField(max_length=512)
    label = models.CharField(max_length=512, help_text="Display name; comes from sources, may be any text.")
    attributes = models.JSONField(default=dict, blank=True)
    owner_team = models.CharField(max_length=100, blank=True)
    # True once someone set the owner by hand; ownership rules then leave it alone.
    owner_locked = models.BooleanField(default=False)
    tags = models.ManyToManyField(Tag, blank=True, related_name="assets")
    first_seen_at = models.DateTimeField(default=clock.now)
    last_seen_at = models.DateTimeField(default=clock.now)
    created_at = models.DateTimeField(default=clock.now)
    updated_at = models.DateTimeField(default=clock.now)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = OrgScopedQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org", "kind", "key"], name="uq_asset_org_kind_key")
        ]
        indexes = [models.Index(fields=["org", "last_seen_at"], name="ix_asset_org_last_seen")]

    def __str__(self) -> str:
        return f"{self.kind}:{self.key}"


class AssetSource(models.Model):
    """Provenance: one row per (asset, source) that reported it."""

    class Kind(models.TextChoices):
        ZONE_FILE = "zone_file"
        NIMBUS = "nimbus"
        CT_FEED = "ct_feed"
        PORT_SCAN = "port_scan"
        API = "api"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="sources")
    source_kind = models.CharField(max_length=32, choices=Kind.choices)
    source_name = models.CharField(max_length=200)
    external_id = models.CharField(max_length=200, blank=True)
    raw = models.JSONField(default=dict, blank=True, help_text="Attributes from the last observation.")
    first_seen_at = models.DateTimeField(default=clock.now)
    last_seen_at = models.DateTimeField(default=clock.now)

    objects = AssetChildQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "source_kind", "source_name"], name="uq_source_asset_kind_name"
            )
        ]


class AssetLink(models.Model):
    class Relation(models.TextChoices):
        RESOLVES_TO = "resolves_to"  # host -> ip
        CNAME = "cname"  # host -> host
        COVERS = "covers"  # certificate -> host
        CONTAINS = "contains"  # network -> ip
        ATTACHED = "attached"  # cloud_resource -> ip / host

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="links_out")
    target = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="links_in")
    relation = models.CharField(max_length=32, choices=Relation.choices)
    source_kind = models.CharField(max_length=32, choices=AssetSource.Kind.choices)
    first_seen_at = models.DateTimeField(default=clock.now)
    last_seen_at = models.DateTimeField(default=clock.now)

    objects = AssetChildQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "target", "relation"], name="uq_link_asset_target_relation"
            )
        ]


class AssetService(models.Model):
    """An open port seen on an ip or host asset."""

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="services")
    port = models.PositiveIntegerField()
    protocol = models.CharField(max_length=8, default="tcp")
    service = models.CharField(max_length=64, blank=True)
    product = models.CharField(max_length=200, blank=True)
    banner = models.CharField(max_length=512, blank=True)
    first_seen_at = models.DateTimeField(default=clock.now)
    last_seen_at = models.DateTimeField(default=clock.now)
    closed_at = models.DateTimeField(null=True, blank=True)

    objects = AssetChildQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "port", "protocol"], name="uq_service_asset_port_protocol"
            )
        ]


class OwnershipRule(models.Model):
    class PatternType(models.TextChoices):
        HOSTNAME = "hostname"  # glob on the key, e.g. "*.payments.harborview-bank.example.test"
        CIDR = "cidr"  # ip assets inside the network
        TAG = "tag"  # assets carrying the tag

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="ownership_rules")
    pattern_type = models.CharField(max_length=16, choices=PatternType.choices)
    pattern = models.CharField(max_length=253)
    team = models.CharField(max_length=100)
    priority = models.IntegerField(default=100, help_text="Lower wins; ties go to the older rule.")
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=clock.now)

    objects = OrgScopedQuerySet.as_manager()

    class Meta:
        ordering = ["priority", "id"]


class AssetChange(models.Model):
    """Append-only history of an asset; also the input of webhook events."""

    class Kind(models.TextChoices):
        CREATED = "created"
        UPDATED = "updated"
        SOURCE_ADDED = "source_added"
        LINK_ADDED = "link_added"
        SERVICE_OPENED = "service_opened"
        SERVICE_CLOSED = "service_closed"
        OWNER_CHANGED = "owner_changed"
        TAGGED = "tagged"
        UNTAGGED = "untagged"
        EXPOSURE_OPENED = "exposure_opened"
        EXPOSURE_RESOLVED = "exposure_resolved"
        ARCHIVED = "archived"

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="asset_changes")
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="changes")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    field = models.CharField(max_length=64, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    source_kind = models.CharField(max_length=32, blank=True)
    job = models.ForeignKey("jobs.Job", null=True, blank=True, on_delete=models.SET_NULL)
    occurred_at = models.DateTimeField(default=clock.now)

    objects = OrgScopedQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["org", "occurred_at"], name="ix_change_org_occurred"),
            models.Index(fields=["asset", "occurred_at"], name="ix_change_asset_occurred"),
        ]


class SavedView(models.Model):
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="saved_views")
    # Null: shared with the whole org (always the case for views made through the API).
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE
    )
    name = models.CharField(max_length=100)
    querystring = models.CharField(max_length=2000, help_text="Canonical asset-list filters.")
    created_at = models.DateTimeField(default=clock.now)

    objects = OrgScopedQuerySet.as_manager()

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "owner", "name"], name="uq_view_org_owner_name", nulls_distinct=False
            )
        ]
