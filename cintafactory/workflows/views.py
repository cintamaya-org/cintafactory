from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.views.generic import TemplateView

from .models import Workflow


class WorkflowBoardView(LoginRequiredMixin, TemplateView):
    """Display the DAT validation workflow as a Kanban board."""

    template_name = "workflows/board.html"
    workflow_code = "dat-validation"

    @cached_property
    def workflow(self) -> Workflow:
        queryset = (
            Workflow.objects.filter(code=self.workflow_code, is_active=True)
            .select_related("content_type")
            .prefetch_related(
                "steps__permissions__role",
                "steps__permissions__user",
            )
        )
        return get_object_or_404(queryset)

    @cached_property
    def workflow_model(self):
        return self.workflow.content_type.model_class()

    def get_columns(self):
        model = self.workflow_model
        if model is None:
            return []

        field_names = {field.name for field in model._meta.get_fields() if not field.many_to_many}
        order_by = "-updated_at" if "updated_at" in field_names else "-pk"
        dat_queryset = model.objects.all().order_by(order_by)

        relation_field_names = {
            field.name
            for field in model._meta.fields
            if field.is_relation and not field.many_to_many and field.related_model is not None
        }
        if "owner" in relation_field_names:
            dat_queryset = dat_queryset.select_related("owner")

        columns = []
        for step in self.workflow.steps.all():
            items = dat_queryset.filter(status=step.state)
            columns.append(
                {
                    "step": step,
                    "items": items,
                    "read_permissions": step.read_permissions,
                    "write_permissions": step.write_permissions,
                }
            )
        return columns

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status_choices = []
        model = self.workflow_model
        if model is not None:
            try:
                status_field = model._meta.get_field("status")
                status_choices = list(status_field.flatchoices)
            except Exception:
                status_choices = []
        context.update(
            {
                "workflow": self.workflow,
                "columns": self.get_columns(),
                "all_statuses": status_choices,
            }
        )
        return context
