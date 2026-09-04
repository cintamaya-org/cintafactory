from __future__ import annotations

from django.db import transaction

from workflows.services import ensure_workflow_instance

from .models import DatViewflowProcess


def ensure_dat_viewflow_process(dat) -> DatViewflowProcess:
    """Compatibility link to authoritative generic workflow instance.

    dat_viewflow now owns display overrides only. Lifecycle execution belongs to
    workflows.services, preventing two workflow engines from drifting.
    """

    workflow_instance = ensure_workflow_instance(dat)
    obj, _created = DatViewflowProcess.objects.update_or_create(
        dat=dat,
        defaults={"process_id": workflow_instance.pk},
    )
    return obj


def enqueue_dat_viewflow_link(dat) -> None:
    transaction.on_commit(lambda: ensure_dat_viewflow_process(dat))
