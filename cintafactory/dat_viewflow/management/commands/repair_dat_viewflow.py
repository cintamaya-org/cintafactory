from __future__ import annotations

from django.core.management.base import BaseCommand

from dat.models import DAT
from dat_viewflow.models import DatViewflowProcess
from dat_viewflow.services import ensure_dat_viewflow_process


class Command(BaseCommand):
    help = "Repair DAT viewflow links (ensure exactly one link and fill missing process IDs)."

    def add_arguments(self, parser):
        parser.add_argument("--dat-id", dest="dat_id", help="Repair a single DAT by UUID")
        parser.add_argument("--dry-run", action="store_true", help="Show what would change without saving")

    def handle(self, *args, **options):
        dat_id = options.get("dat_id")
        dry_run = options.get("dry_run")

        dats = DAT.objects.all().order_by("created_at")
        if dat_id:
            dats = dats.filter(pk=dat_id)

        repaired = 0
        skipped = 0

        for dat in dats.iterator():
            if dry_run:
                link = DatViewflowProcess.objects.filter(dat=dat).first()
                if link and link.process_id:
                    skipped += 1
                    continue
                self.stdout.write(f"Would repair DAT {dat.pk}")
                repaired += 1
                continue

            ensure_dat_viewflow_process(dat)
            link = DatViewflowProcess.objects.filter(dat=dat).first()
            if link and link.process_id:
                repaired += 1
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(f"Repaired: {repaired}, Skipped: {skipped}"))
