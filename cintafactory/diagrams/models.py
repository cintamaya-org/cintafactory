from django.conf import settings
from django.db import models
from django.utils import timezone

from .validation import sanitize_diagram_title


def thumbnail_upload_to(instance, filename):
    return f"diagrams/{instance.id}/thumb.png"


class Diagram(models.Model):
    title = models.CharField(max_length=200)
    xml = models.TextField(blank=True, default="")
    thumbnail = models.ImageField(upload_to=thumbnail_upload_to, blank=True, null=True)
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

    def __str__(self) -> str:
        return self.title
