from __future__ import annotations

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _


class Workflow(models.Model):
    """Declarative workflow definition bound to a concrete Django model."""

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="workflows",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workflow_definition"
        ordering = ["name"]
        verbose_name = _("Workflow")
        verbose_name_plural = _("Workflows")

    def __str__(self) -> str:  # pragma: no cover - human readable helper
        return self.name


class WorkflowStep(models.Model):
    """Single workflow column/state displayed on the Kanban board."""

    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name="steps",
    )
    key = models.SlugField(max_length=64)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    state = models.CharField(
        max_length=64,
        help_text=_("Code stored on the target object to represent this step"),
    )
    is_initial = models.BooleanField(
        default=False,
        help_text=_("Whether this step is the default/start of the workflow."),
    )

    class Meta:
        db_table = "workflow_step"
        ordering = ["order", "pk"]
        unique_together = (
            ("workflow", "key"),
            ("workflow", "state"),
        )
        verbose_name = _("Workflow step")
        verbose_name_plural = _("Workflow steps")

    def __str__(self) -> str:  # pragma: no cover - human readable helper
        return f"{self.workflow}: {self.name}"

    def permissions_by_type(self, permission_type: str) -> models.QuerySet["WorkflowStepPermission"]:
        return self.permissions.filter(permission_type=permission_type).select_related("role", "user")

    @property
    def read_permissions(self) -> models.QuerySet["WorkflowStepPermission"]:
        return self.permissions_by_type(WorkflowStepPermission.PERMISSION_READ)

    @property
    def write_permissions(self) -> models.QuerySet["WorkflowStepPermission"]:
        return self.permissions_by_type(WorkflowStepPermission.PERMISSION_WRITE)


class WorkflowStepPermission(models.Model):
    """Role/user assignments for workflow steps."""

    PERMISSION_READ = "read"
    PERMISSION_WRITE = "write"
    PERMISSION_CHOICES = [
        (PERMISSION_READ, _("Read")),
        (PERMISSION_WRITE, _("Write")),
    ]

    step = models.ForeignKey(
        WorkflowStep,
        on_delete=models.CASCADE,
        related_name="permissions",
    )
    permission_type = models.CharField(max_length=5, choices=PERMISSION_CHOICES)
    role = models.ForeignKey(
        "users.Role",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="workflow_step_permissions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="workflow_step_permissions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "workflow_step_permission"
        constraints = [
            models.CheckConstraint(
                check=models.Q(role__isnull=False) | models.Q(user__isnull=False),
                name="workflow_step_permission_role_or_user",
            ),
            models.UniqueConstraint(
                fields=["step", "permission_type", "role"],
                condition=models.Q(role__isnull=False),
                name="workflow_step_permission_unique_role",
            ),
            models.UniqueConstraint(
                fields=["step", "permission_type", "user"],
                condition=models.Q(user__isnull=False),
                name="workflow_step_permission_unique_user",
            ),
        ]
        ordering = ["step", "permission_type", "role__name", "user__username"]
        verbose_name = _("Workflow step permission")
        verbose_name_plural = _("Workflow step permissions")

    def __str__(self) -> str:  # pragma: no cover - human readable helper
        if self.role:
            subject = self.role.name
        elif self.user:
            subject = self.user.get_username()
        else:
            subject = _("Unknown")
        return f"{subject} → {self.step} ({self.get_permission_type_display()})"

    @property
    def subject(self) -> str:
        if self.role:
            return self.role.name
        if self.user:
            return self.user.get_username()
        return _("Unknown")
