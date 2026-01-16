from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from urllib.error import HTTPError

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import migrations, models
from django.utils import timezone

from cintafactory.seaweedfs_storage import SeaweedFSStorage

import diagrams.models

logger = logging.getLogger(__name__)


def _migrate_drawio_files(apps, schema_editor):
    Diagram = apps.get_model("diagrams", "Diagram")
    storage = SeaweedFSStorage()
    local_storage = FileSystemStorage(location=settings.MEDIA_ROOT)
    for diagram in Diagram.objects.all():
        updated_fields = []
        xml_payload = getattr(diagram, "xml", "") or ""
        if xml_payload:
            raw = xml_payload.encode("utf-8")
            storage_name = f"diagrams/{diagram.pk}/diagram.drawio"
            try:
                if not storage.exists(storage_name):
                    storage.save(storage_name, ContentFile(raw))
            except HTTPError as exc:
                logger.warning("SeaweedFS upload failed for diagram %s xml: %s", diagram.pk, exc)
                raise
            diagram.xml_file = storage_name
            diagram.xml_size = len(raw)
            diagram.xml_content_type = "application/xml"
            updated_fields.extend(["xml_file", "xml_size", "xml_content_type"])

        thumb_field = getattr(diagram, "thumbnail", None)
        thumb_name = getattr(thumb_field, "name", "") if thumb_field else ""
        if thumb_name:
            try:
                exists_in_storage = storage.exists(thumb_name)
            except HTTPError as exc:
                logger.warning("SeaweedFS head failed for thumbnail %s: %s", thumb_name, exc)
                raise
            if not exists_in_storage and local_storage.exists(thumb_name):
                try:
                    with local_storage.open(thumb_name, "rb") as existing:
                        raw_thumb = existing.read()
                    storage.save(thumb_name, ContentFile(raw_thumb))
                except HTTPError as exc:
                    logger.warning("SeaweedFS upload failed for thumbnail %s: %s", thumb_name, exc)
                    raise
                except Exception as exc:
                    logger.warning("Unable to read existing thumbnail %s: %s", thumb_name, exc)
            try:
                if storage.exists(thumb_name):
                    diagram.thumbnail = thumb_name
                    if "thumbnail" not in updated_fields:
                        updated_fields.append("thumbnail")
                    diagram.thumbnail_size = storage.size(thumb_name)
                    diagram.thumbnail_content_type = mimetypes.guess_type(thumb_name)[0] or "image/png"
                    updated_fields.extend(["thumbnail_size", "thumbnail_content_type"])
            except HTTPError as exc:
                logger.warning("SeaweedFS metadata lookup failed for thumbnail %s: %s", thumb_name, exc)
                raise

        if updated_fields:
            diagram.updated_at = timezone.now()
            updated_fields.append("updated_at")
            diagram.save(update_fields=updated_fields)


def _migrate_likec4_files(apps, schema_editor):
    LikeC4File = apps.get_model("diagrams", "LikeC4File")
    storage = SeaweedFSStorage()
    root = Path(settings.BASE_DIR).parent / "likec4"
    data_root = root / "data"
    if not data_root.exists():
        return
    for file_path in data_root.rglob("*.c4"):
        try:
            relative_path = file_path.relative_to(root).as_posix()
        except ValueError:
            continue
        try:
            raw = file_path.read_bytes()
        except OSError as exc:
            logger.warning("Unable to read LikeC4 file %s: %s", file_path, exc)
            continue
        try:
            if not storage.exists(relative_path):
                storage.save(relative_path, ContentFile(raw))
        except HTTPError as exc:
            logger.warning("SeaweedFS upload failed for LikeC4 file %s: %s", relative_path, exc)
            raise
        LikeC4File.objects.update_or_create(
            storage_path=relative_path,
            defaults={
                "content_type": "text/plain",
                "size": len(raw),
                "updated_at": timezone.now(),
            },
        )


def migrate_diagram_assets(apps, schema_editor):
    _migrate_drawio_files(apps, schema_editor)
    _migrate_likec4_files(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [
        ("diagrams", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="diagram",
            name="xml_file",
            field=models.FileField(
                blank=True,
                null=True,
                storage=SeaweedFSStorage(),
                upload_to=diagrams.models.drawio_upload_to,
            ),
        ),
        migrations.AddField(
            model_name="diagram",
            name="xml_content_type",
            field=models.CharField(blank=True, default="application/xml", max_length=120),
        ),
        migrations.AddField(
            model_name="diagram",
            name="xml_size",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="diagram",
            name="thumbnail_content_type",
            field=models.CharField(blank=True, default="image/png", max_length=120),
        ),
        migrations.AddField(
            model_name="diagram",
            name="thumbnail_size",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="LikeC4File",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("storage_path", models.CharField(max_length=500, unique=True)),
                ("content_type", models.CharField(blank=True, max_length=200)),
                ("size", models.PositiveBigIntegerField(default=0)),
                ("updated_at", models.DateTimeField(default=timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.RunPython(migrate_diagram_assets, migrations.RunPython.noop),
    ]
