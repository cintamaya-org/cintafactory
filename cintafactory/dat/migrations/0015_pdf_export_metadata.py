from __future__ import annotations

import logging
import os
from urllib.error import HTTPError

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import migrations, models
from django.utils.text import slugify

from cintafactory.seaweedfs_storage import SeaweedFSStorage

logger = logging.getLogger(__name__)


def _dat_pdf_export_basename(dat) -> str:
    base = slugify(getattr(dat, "reference", "") or getattr(dat, "title", "")) or f"dat-{dat.pk}"
    return f"{base}.pdf"


def _dat_pdf_export_path(dat) -> str:
    basename = _dat_pdf_export_basename(dat)
    return os.path.join("dat_exports", str(dat.pk), basename)


def migrate_pdf_exports(apps, schema_editor):
    DAT = apps.get_model("dat", "DAT")
    storage = SeaweedFSStorage()
    local_storage = FileSystemStorage(location=settings.MEDIA_ROOT)
    for dat in DAT.objects.all():
        path = _dat_pdf_export_path(dat)
        raw_size = 0
        stored = False
        if local_storage.exists(path):
            try:
                with local_storage.open(path, "rb") as existing:
                    raw = existing.read()
                raw_size = len(raw)
            except Exception as exc:
                logger.warning("Unable to read local PDF export %s: %s", path, exc)
                raw = None
            if raw is not None:
                try:
                    if not storage.exists(path):
                        storage.save(path, ContentFile(raw))
                    stored = True
                except HTTPError as exc:
                    logger.warning("SeaweedFS upload failed for DAT %s export: %s", dat.pk, exc)
                    raise
        if not stored:
            try:
                if storage.exists(path):
                    raw_size = storage.size(path)
                    stored = True
            except HTTPError as exc:
                logger.warning("SeaweedFS lookup failed for DAT %s export: %s", dat.pk, exc)
                raise
        if stored:
            dat.pdf_export_path = path
            dat.pdf_export_size = raw_size
            dat.pdf_export_content_type = "application/pdf"
            dat.save(
                update_fields=["pdf_export_path", "pdf_export_size", "pdf_export_content_type", "updated_at"]
            )


class Migration(migrations.Migration):
    dependencies = [
        ("dat", "0014_merge_20260112_1658"),
    ]

    operations = [
        migrations.AddField(
            model_name="dat",
            name="pdf_export_path",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="dat",
            name="pdf_export_content_type",
            field=models.CharField(blank=True, default="application/pdf", max_length=120),
        ),
        migrations.AddField(
            model_name="dat",
            name="pdf_export_size",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.RunPython(migrate_pdf_exports, migrations.RunPython.noop),
    ]
