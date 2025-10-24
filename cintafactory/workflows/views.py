from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.views.generic import TemplateView

from dat.models import DATStatus

from .models import Workflow


class WorkflowBoardView(LoginRequiredMixin, TemplateView):
    """Display the DAT validation workflow as a Kanban board."""

    template_name = "workflows/board.html"
    workflow_code = "dat-validation"
    initial_status = DATStatus.BESOIN_DAL
    completed_statuses = {
        DATStatus.DAT_VALIDE,
        DATStatus.PRESENTATION_COMITE,
        DATStatus.LEVEE_RESERVE,
        DATStatus.DAT_PUBLIE,
    }
    column_titles = {
        "initial": "Nouveau besoin (DAL)",
        "in_progress": "Projets en cours",
        "completed": "Projets terminés",
    }

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

    @staticmethod
    def _aggregate_permissions(steps, accessor: str):
        aggregated = []
        seen = set()
        for step in steps:
            for permission in getattr(step, accessor).all():
                pk = getattr(permission, "pk", None)
                if pk is not None:
                    if pk in seen:
                        continue
                    seen.add(pk)
                aggregated.append(permission)
        return aggregated

    def _build_column(self, *, key, states, step_by_state, dat_queryset):
        steps = [step_by_state[state] for state in states if state in step_by_state]
        status_codes = [step.state for step in steps]
        if status_codes:
            items = dat_queryset.filter(status__in=status_codes)
        else:
            items = dat_queryset.none()
        description = steps[0].description if len(steps) == 1 else ""
        return {
            "key": key,
            "title": self.column_titles[key],
            "description": description,
            "status_codes": status_codes,
            "status_labels": [step.name for step in steps],
            "items": items,
            "read_permissions": self._aggregate_permissions(steps, "read_permissions"),
            "write_permissions": self._aggregate_permissions(steps, "write_permissions"),
        }

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

        steps = list(self.workflow.steps.all())
        step_by_state = {step.state: step for step in steps}

        initial_states = [self.initial_status] if self.initial_status in step_by_state else []
        completed_states = [
            step.state for step in steps if step.state in self.completed_statuses
        ]
        excluded_states = set(initial_states + completed_states)
        in_progress_states = [step.state for step in steps if step.state not in excluded_states]

        return [
            self._build_column(
                key="initial",
                states=initial_states,
                step_by_state=step_by_state,
                dat_queryset=dat_queryset,
            ),
            self._build_column(
                key="in_progress",
                states=in_progress_states,
                step_by_state=step_by_state,
                dat_queryset=dat_queryset,
            ),
            self._build_column(
                key="completed",
                states=completed_states,
                step_by_state=step_by_state,
                dat_queryset=dat_queryset,
            ),
        ]

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
