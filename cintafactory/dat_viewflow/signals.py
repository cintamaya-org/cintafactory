from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from dat.models import DAT

from .services import enqueue_dat_viewflow_link

logger = logging.getLogger(__name__)


@receiver(post_save, sender=DAT)
def link_dat_to_viewflow(sender, instance: DAT, created: bool, **kwargs) -> None:
    if not created:
        return
    try:
        enqueue_dat_viewflow_link(instance)
    except Exception:
        logger.exception("Unable to link DAT %s to viewflow workflow", instance.pk)
