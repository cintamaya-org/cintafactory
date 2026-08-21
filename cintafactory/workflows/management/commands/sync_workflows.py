from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from workflows.sync import sync_workflow_definitions


class Command(BaseCommand):
    help = "Synchronise declarative workflow definitions with the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Validate and preview synchronization, then roll back all database writes.",
        )

    def handle(self, *args, **options):
        if options["check"]:
            with transaction.atomic():
                sync_workflow_definitions()
                transaction.set_rollback(True)
            self.stdout.write(self.style.SUCCESS("Workflow definitions are valid; no changes saved."))
            return
        sync_workflow_definitions()
        self.stdout.write(self.style.SUCCESS("Workflow definitions synchronised and published."))
