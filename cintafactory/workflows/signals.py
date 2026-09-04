from __future__ import annotations

import logging

from django.db.models.signals import post_migrate
from django.dispatch import receiver

from .sync import sync_workflow_definitions

logger = logging.getLogger(__name__)


@receiver(post_migrate)
def sync_workflows_on_migrate(sender, **kwargs):
    """
    Keep declarative workflow definitions and DB state aligned.

    post_migrate is used to avoid hitting the database before migrations are
    applied. Errors are logged instead of raised in order to keep migrations
    resilient: an operator can fix the issue and re-run sync later.
    """

    # Avoid executing for unrelated apps.
    if getattr(sender, "label", None) != "workflows":
        return

    try:
        sync_workflow_definitions()
    except Exception:
        logger.exception("Unable to synchronise workflow definitions after migrations.")
