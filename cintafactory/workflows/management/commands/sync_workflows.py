from __future__ import annotations

from django.core.management.base import BaseCommand

from workflows.sync import sync_workflow_definitions


class Command(BaseCommand):
    help = "Synchronise declarative workflow definitions with the database."

    def handle(self, *args, **options):
        sync_workflow_definitions()
        self.stdout.write(self.style.SUCCESS("Workflow definitions synchronised."))
