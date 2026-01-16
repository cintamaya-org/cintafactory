from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone

from cintafactory.seaweedfs_storage import SeaweedFSStorage

from .validation import sanitize_diagram_title


def get_diagram_storage() -> SeaweedFSStorage:
    return SeaweedFSStorage()


def get_diagram_thumbnail_storage() -> SeaweedFSStorage:
    return SeaweedFSStorage(public_url=settings.SEAWEEDFS_PUBLIC_URL_PP)


def thumbnail_upload_to(instance, filename):
    return f"diagrams/{instance.id}/thumb.png"


def likec4_png_path_for(storage_path: str) -> str:
    path = Path(storage_path)
    parts = path.parts
    if len(parts) >= 3 and parts[0] == "diagrams":
        return f"diagrams/{parts[1]}/thumb.png"
    base = path.name
    if base.lower().endswith(".c4"):
        base = base[:-3]
    return f"diagrams/likec4/{base}.png"


def drawio_upload_to(instance, filename):
    return f"diagrams/{instance.id}/diagram.drawio"


class Diagram(models.Model):
    title = models.CharField(max_length=200)
    xml_file = models.FileField(
        upload_to=drawio_upload_to,
        storage=get_diagram_storage(),
        blank=True,
        null=True,
    )
    xml_content_type = models.CharField(max_length=120, blank=True, default="application/xml")
    xml_size = models.PositiveIntegerField(default=0)
    thumbnail = models.ImageField(
        upload_to=thumbnail_upload_to,
        storage=get_diagram_thumbnail_storage(),
        blank=True,
        null=True,
    )
    thumbnail_content_type = models.CharField(max_length=120, blank=True, default="image/png")
    thumbnail_size = models.PositiveIntegerField(default=0)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="diagrams",
    )
    updated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated_at"]

    def clean(self):
        super().clean()
        self.title = sanitize_diagram_title(self.title)

    def read_xml(self) -> str:
        field = getattr(self, "xml_file", None)
        if not field or not getattr(field, "name", None):
            return ""
        try:
            field.open("rb")
            raw = field.read()
        except FileNotFoundError:
            return ""
        except Exception:
            return ""
        finally:
            try:
                field.close()
            except Exception:
                pass
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="ignore")

    def write_xml(self, xml_payload: str, *, content_type: str = "application/xml") -> None:
        payload = xml_payload or ""
        raw = payload.encode("utf-8")
        self.xml_file.save("diagram.drawio", ContentFile(raw), save=False)
        self.xml_size = len(raw)
        self.xml_content_type = content_type
        self.updated_at = timezone.now()
        self.save(update_fields=["xml_file", "xml_size", "xml_content_type", "updated_at"])

    def __str__(self) -> str:
        return self.title


class LikeC4File(models.Model):
    storage_path = models.CharField(max_length=500, unique=True)
    content_type = models.CharField(max_length=200, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    png_path = models.CharField(max_length=500, blank=True, default="")
    png_content_type = models.CharField(max_length=200, blank=True, default="image/png")
    png_size = models.PositiveBigIntegerField(default=0)
    png_updated_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.storage_path
