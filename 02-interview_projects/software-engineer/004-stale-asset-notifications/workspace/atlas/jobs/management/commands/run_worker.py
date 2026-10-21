import os
import signal
import socket
import threading

from django.conf import settings
from django.core.management.base import BaseCommand

from atlas.jobs.worker import run_forever, run_once


class Command(BaseCommand):
    help = "Run queued jobs (imports, exposure evaluation) and deliver due webhooks."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run one iteration and exit.")
        parser.add_argument("--worker-id", default=f"{socket.gethostname()}:{os.getpid()}")

    def handle(self, *args, once: bool, worker_id: str, **options):
        if once:
            ran = run_once(worker_id)
            self.stdout.write("ran one job" if ran else "no job due")
            return
        stop = threading.Event()
        for signum in (signal.SIGTERM, signal.SIGINT):
            # Finish the current job, then exit (docker compose stop sends SIGTERM).
            signal.signal(signum, lambda *_: stop.set())
        run_forever(worker_id, poll_seconds=settings.ATLAS_WORKER_POLL_SECONDS, stop=stop)
