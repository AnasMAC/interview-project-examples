from django.core.management.base import BaseCommand, CommandError

from atlas.core.models import Org
from atlas.jobs.handlers import PermanentJobError, resolve_import_path
from atlas.jobs.queue import enqueue


class Command(BaseCommand):
    help = "Queue an import of a file under ATLAS_IMPORT_ROOT for one org."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Org slug.")
        parser.add_argument("--importer", required=True, help="zone_file, nimbus, ct_feed or port_scan.")
        parser.add_argument("--path", required=True, help="Path relative to ATLAS_IMPORT_ROOT.")
        parser.add_argument("--source-name", default="", help="Overrides the importer's source name.")

    def handle(self, *args, org: str, importer: str, path: str, source_name: str, **options):
        from atlas.importers.registry import IMPORTERS

        organization = Org.objects.filter(slug=org).first()
        if organization is None:
            raise CommandError(f"unknown org {org!r}")
        if importer not in IMPORTERS:
            raise CommandError(f"unknown importer {importer!r}; choose from {', '.join(sorted(IMPORTERS))}")
        try:
            resolve_import_path(path)
        except PermanentJobError as error:
            raise CommandError(str(error)) from None
        payload = {"importer": importer, "path": path}
        if source_name:
            payload["source_name"] = source_name
        job = enqueue(organization, "import.run", payload)
        self.stdout.write(f"queued job {job.id} ({importer} {path} for {org})")
