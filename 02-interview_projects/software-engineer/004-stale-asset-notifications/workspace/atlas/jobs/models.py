from django.db import models

from atlas.core import clock
from atlas.core.models import Org, OrgScopedQuerySet


class Job(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        DONE = "done"
        FAILED = "failed"  # will be retried at run_after
        DEAD = "dead"  # gave up after max_attempts

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="jobs")
    kind = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    run_after = models.DateTimeField(default=clock.now)
    locked_by = models.CharField(max_length=100, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=clock.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    objects = OrgScopedQuerySet.as_manager()

    class Meta:
        indexes = [models.Index(fields=["status", "run_after"], name="ix_job_status_run_after")]

    def __str__(self) -> str:
        return f"job {self.pk} {self.kind} ({self.status})"
