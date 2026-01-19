from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.error import HTTPError

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from cintafactory.seaweedfs_storage import SeaweedFSStorage
from diagrams.models import LikeC4Diagram


class Command(BaseCommand):
    help = "Upload LikeC4 .c4 files from likec4/data to SeaweedFS storage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--root",
            dest="root",
            default=None,
            help="Override the LikeC4 root folder (default: <BASE_DIR>/../likec4).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List files that would be uploaded without writing to SeaweedFS.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite existing files in SeaweedFS.",
        )
        parser.add_argument(
            "--delete-local",
            action="store_true",
            help="Delete local files after a successful upload.",
        )

    def handle(self, *args, **options):
        root_override = options["root"]
        root = Path(root_override) if root_override else Path(settings.BASE_DIR).parent / "likec4"
        data_root = root / "data"
        if not data_root.exists():
            self.stdout.write(self.style.WARNING(f"LikeC4 data folder not found: {data_root}"))
            return

        storage = SeaweedFSStorage()
        dry_run = bool(options["dry_run"])
        overwrite = bool(options["overwrite"])
        delete_local = bool(options["delete_local"])

        uploaded = 0
        skipped = 0
        for file_path in sorted(data_root.rglob("*.c4")):
            try:
                relative_path = file_path.relative_to(root).as_posix()
            except ValueError:
                skipped += 1
                continue

            try:
                raw = file_path.read_bytes()
            except OSError as exc:
                skipped += 1
                self.stderr.write(f"Unable to read {file_path}: {exc}")
                continue

            content_type = mimetypes.guess_type(file_path.name)[0] or "text/plain"
            size = len(raw)

            if dry_run:
                self.stdout.write(f"[dry-run] upload {relative_path} ({size} bytes)")
                continue

            try:
                should_upload = overwrite or not storage.exists(relative_path)
            except HTTPError as exc:
                self.stderr.write(f"SeaweedFS check failed for {relative_path}: {exc}")
                raise

            if should_upload:
                try:
                    content = ContentFile(raw, name=file_path.name)
                    content.content_type = content_type
                    storage.save(relative_path, content)
                    uploaded += 1
                except HTTPError as exc:
                    self.stderr.write(f"SeaweedFS upload failed for {relative_path}: {exc}")
                    raise
            else:
                skipped += 1

            LikeC4Diagram.objects.update_or_create(
                storage_path=relative_path,
                defaults={
                    "content_type": content_type,
                    "size": size,
                    "updated_at": timezone.now(),
                },
            )

            if delete_local and should_upload:
                try:
                    file_path.unlink()
                except OSError as exc:
                    self.stderr.write(f"Unable to delete {file_path}: {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                f"LikeC4 migration done. Uploaded: {uploaded}, skipped: {skipped}."
            )
        )
