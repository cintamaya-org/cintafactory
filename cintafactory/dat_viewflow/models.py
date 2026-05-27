from __future__ import annotations

from django.db import models


class DatViewflowProcess(models.Model):
    dat = models.OneToOneField(
        "dat.DAT",
        on_delete=models.CASCADE,
        related_name="viewflow_process",
    )
    process_id = models.UUIDField(null=True, blank=True)
    workflow_config = models.JSONField(default=dict, blank=True)
    workflow_data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "dat_viewflow_process"
        verbose_name = "DAT Viewflow process"
        verbose_name_plural = "DAT Viewflow processes"
