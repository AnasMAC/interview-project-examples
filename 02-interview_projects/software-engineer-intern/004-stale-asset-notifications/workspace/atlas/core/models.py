from django.conf import settings
from django.db import models

from atlas.core import clock


class OrgScopedQuerySet(models.QuerySet):
    """Every customer-data query starts with ``for_org(org)``.

    Models without their own ``org`` column set ``org_lookup`` on a subclass
    (for example ``asset__org``).
    """

    org_lookup = "org"

    def for_org(self, org):
        return self.filter(**{self.org_lookup: org})


def default_allowed_ports() -> list[int]:
    return [80, 443]


class Org(models.Model):
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    domain = models.CharField(max_length=253, help_text="Primary customer domain.")
    timezone = models.CharField(max_length=64, default="UTC", help_text="IANA name.")
    allowed_ports = models.JSONField(default=default_allowed_ports)
    cert_warning_days = models.PositiveSmallIntegerField(default=30)
    created_at = models.DateTimeField(default=clock.now)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.slug


class ApiKey(models.Model):
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=16, db_index=True)
    key_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=clock.now)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = OrgScopedQuerySet.as_manager()

    def __str__(self) -> str:
        return f"{self.org.slug}:{self.name} ({self.prefix}...)"


class Membership(models.Model):
    """Gives a dashboard user access to one org."""

    class Role(models.TextChoices):
        VIEWER = "viewer"
        EDITOR = "editor"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.EDITOR)
    created_at = models.DateTimeField(default=clock.now)

    objects = OrgScopedQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "org"], name="uq_membership_user_org")
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.org.slug}"
