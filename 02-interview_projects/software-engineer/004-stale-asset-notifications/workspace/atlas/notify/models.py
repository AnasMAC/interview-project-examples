from django.db import models

from atlas.core import clock
from atlas.core.models import Org, OrgScopedQuerySet

EVENTS = [
    "asset.created",
    "asset.changed",
    "exposure.opened",
    "exposure.resolved",
    "import.completed",
]


class Webhook(models.Model):
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="webhooks")
    name = models.CharField(max_length=100)
    url = models.URLField(max_length=500)
    secret = models.CharField(max_length=100, help_text="HMAC key; never returned by the API.")
    events = models.JSONField(default=list, help_text="Subset of notify.models.EVENTS.")
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=clock.now)

    objects = OrgScopedQuerySet.as_manager()

    def __str__(self) -> str:
        return f"{self.org.slug}:{self.name}"


class OutboxEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        DELIVERED = "delivered"
        FAILED = "failed"  # retried at next_attempt_at
        DEAD = "dead"

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="outbox_events")
    webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name="outbox_events")
    event = models.CharField(max_length=64)
    payload = models.JSONField(help_text="The envelope's data object.")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=clock.now)
    last_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(default=clock.now)
    delivered_at = models.DateTimeField(null=True, blank=True)

    objects = OrgScopedQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="ix_outbox_status_next")
        ]
