from django.db import models
from django.db.models import Q

from atlas.assets.models import Asset
from atlas.core import clock
from atlas.core.models import Org, OrgScopedQuerySet


class Exposure(models.Model):
    class Rule(models.TextChoices):
        ADMIN_PANEL_PUBLIC = "admin_panel_public"
        CERT_EXPIRING = "cert_expiring"
        DANGLING_CNAME = "dangling_cname"
        UNEXPECTED_PORT = "unexpected_port"

    class Severity(models.TextChoices):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"
        CRITICAL = "critical"

    class Status(models.TextChoices):
        OPEN = "open"
        RESOLVED = "resolved"

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="exposures")
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="exposures")
    rule = models.CharField(max_length=32, choices=Rule.choices)
    # What on the asset triggered the rule ("8443/tcp", a CNAME target...);
    # "" when the rule can fire only once per asset.
    subject = models.CharField(max_length=253, blank=True)
    severity = models.CharField(max_length=16, choices=Severity.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    title = models.CharField(max_length=300)
    details = models.JSONField(default=dict, blank=True)
    opened_at = models.DateTimeField(default=clock.now)
    last_evaluated_at = models.DateTimeField(default=clock.now)
    resolved_at = models.DateTimeField(null=True, blank=True)

    objects = OrgScopedQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "rule", "subject"],
                condition=Q(status="open"),
                name="uq_exposure_open_asset_rule_subject",
            )
        ]
        indexes = [models.Index(fields=["org", "status"], name="ix_exposure_org_status")]
