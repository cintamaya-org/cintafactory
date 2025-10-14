from __future__ import annotations
from dataclasses import dataclass
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class DATStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    # (future) SUBMITTED = "submitted", "Submitted"
    # (future) APPROVED = "approved", "Approved"
    # (future) REJECTED = "rejected", "Rejected"


class DATSequence(models.Model):
    """
    Tracks the last allocated sequence per calendar year for DAT IDs.
    Example business_id: DAT-2025-0001
    """
    year = models.PositiveIntegerField(primary_key=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "dat_sequence"


def next_business_id() -> str:
    year = timezone.now().year
    with transaction.atomic():
        seq, _ = DATSequence.objects.select_for_update().get_or_create(year=year)
        seq.last_number += 1
        seq.save(update_fields=["last_number"])
        return f"DAT-{year}-{seq.last_number:04d}"


class DAT(models.Model):
    """
    Minimal DAT model for the US:
    - business_id is generated automatically (DAT-YYYY-####)
    - status defaults to Draft
    - created_by is the request owner (Porteur)
    """
    business_id = models.CharField(max_length=20, unique=True, editable=False)
    title = models.CharField(max_length=255)
    # For now keep project as a simple name; later you can switch to FK to your projects app.
    project_name = models.CharField("Project", max_length=255)
    status = models.CharField(max_length=20, choices=DATStatus.choices, default=DATStatus.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_dats")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # convenience flag for future workflow link
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "dat_dat"
        verbose_name = "Technical Architecture Dossier"
        verbose_name_plural = "Technical Architecture Dossiers"

    def save(self, *args, **kwargs):
        if not self.business_id:
            self.business_id = next_business_id()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.business_id} — {self.title}"
