from __future__ import annotations

import logging
import uuid

from django.db import transaction

from .flows import DatViewflowFlow
from .models import DatViewflowProcess

logger = logging.getLogger(__name__)


def ensure_dat_viewflow_process(dat) -> DatViewflowProcess | None:
    with transaction.atomic():
        existing = DatViewflowProcess.objects.select_for_update().filter(dat=dat).first()
        if existing and existing.process_id:
            return existing

    start_node = getattr(DatViewflowFlow, "start", None)
    if start_node is not None and hasattr(start_node, "run"):
        try:
            process = start_node.run(dat=dat)
        except TypeError:
            process = start_node.run(dat_id=str(dat.pk))
        except Exception:
            logger.exception("Unable to start viewflow process for DAT %s", dat.pk)
            return _create_process_fallback(dat, existing=existing)
        return _link_process(dat, process, existing=existing)

    return _create_process_fallback(dat, existing=existing)


def _create_process_fallback(dat, *, existing: DatViewflowProcess | None = None) -> DatViewflowProcess | None:
    logger.warning("Skipping viewflow process creation for DAT %s (no process available)", dat.pk)
    if existing:
        if not existing.process_id:
            existing.process_id = uuid.uuid4()
            existing.save(update_fields=["process_id"])
        return existing
    obj, _created = DatViewflowProcess.objects.get_or_create(dat=dat)
    if not obj.process_id:
        obj.process_id = uuid.uuid4()
        obj.save(update_fields=["process_id"])
    return obj


def _link_process(dat, process, *, existing: DatViewflowProcess | None = None) -> DatViewflowProcess | None:
    if process is None:
        return None
    process_id = getattr(process, "pk", None) or uuid.uuid4()
    if existing:
        if existing.process_id != process_id:
            existing.process_id = process_id
            existing.save(update_fields=["process_id"])
        return existing
    obj, _created = DatViewflowProcess.objects.get_or_create(
        dat=dat,
        defaults={"process_id": process_id},
    )
    if obj.process_id != process_id:
        obj.process_id = process_id
        obj.save(update_fields=["process_id"])
    return obj


def enqueue_dat_viewflow_link(dat) -> None:
    transaction.on_commit(lambda: ensure_dat_viewflow_process(dat))
