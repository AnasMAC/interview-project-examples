"""``python manage.py create_demo_user``: dashboard login ``demo`` / ``DEMO-atlas-demo``.

Idempotent: resets the password and adds any missing membership, so it also repairs the user
after ``seed --reset`` or after new orgs were created.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from atlas.core.models import Membership, Org

USERNAME = "demo"
PASSWORD = "DEMO-atlas-demo"  # noqa: S105 - local demo credential, documented in README


class Command(BaseCommand):
    help = "Create or repair the dashboard demo user (member of every org)."

    def handle(self, *args, **options):
        user, created = get_user_model().objects.get_or_create(
            username=USERNAME, defaults={"email": "demo@brindlecove.example.test", "first_name": "Demo"}
        )
        user.set_password(PASSWORD)
        user.is_active = True
        user.save()
        added = 0
        for org in Org.objects.order_by("id"):
            _, made = Membership.objects.get_or_create(
                user=user, org=org, defaults={"role": Membership.Role.EDITOR}
            )
            added += made
        if not Org.objects.exists():
            self.stderr.write("No orgs yet: run `make seed`, then this command again.")
        verb = "Created" if created else "Updated"
        self.stdout.write(f"{verb} user {USERNAME!r}; {added} membership(s) added.")
