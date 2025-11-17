from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.views.generic import TemplateView

from dat.models import DATStatus
from dat.permissions import filter_dat_queryset_for_user
from dat.views import get_current_responsibles, get_next_status, user_can_progress_dat

from .models import Workflow


class WorkflowOverviewView(LoginRequiredMixin, TemplateView):
    """Static overview describing the workflow journey."""

    template_name = "workflows/overview.html"


class WorkflowBoardView(LoginRequiredMixin, TemplateView):
    """Display the DAT validation workflow as a Kanban board."""

    template_name = "workflows/board.html"
    workflow_code = "dat-validation"
    initial_status = DATStatus.DEMANDE_INITIALE
    completed_statuses = {
        DATStatus.DAT_VALIDE,
        DATStatus.DAT_REFUSE,
    }
    column_titles = {
        "initial": "Nouveau besoin",
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

    def _build_column(self, *, key, states, step_by_state, dat_items):
        steps = [step_by_state[state] for state in states if state in step_by_state]
        status_codes = [step.state for step in steps]
        items = [dat for dat in dat_items if dat.status in status_codes] if status_codes else []
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

    def get_dat_items(self):
        model = self.workflow_model
        if model is None:
            return []

        field_names = {
            field.name for field in model._meta.get_fields() if not field.many_to_many
        }
        order_by = "-updated_at" if "updated_at" in field_names else "-pk"
        dat_queryset = model.objects.all().order_by(order_by)
        dat_queryset = filter_dat_queryset_for_user(dat_queryset, self.request.user)
        dat_queryset = dat_queryset.prefetch_related("participants__role", "participants__user")

        relation_field_names = {
            field.name
            for field in model._meta.fields
            if field.is_relation
            and not field.many_to_many
            and field.related_model is not None
        }
        if "owner" in relation_field_names:
            dat_queryset = dat_queryset.select_related("owner")

        dat_items = list(dat_queryset)

        for dat in dat_items:
            dat.can_progress = user_can_progress_dat(dat, self.request.user)
            next_status = get_next_status(dat.status)
            dat.next_status = next_status
            if next_status:
                try:
                    dat.next_status_label = DATStatus(next_status).label
                except ValueError:
                    dat.next_status_label = ""
            else:
                dat.next_status_label = ""
            responsibles = get_current_responsibles(dat)
            dat.current_responsibles = responsibles
            assigned_labels = [
                item["user_display"] for item in responsibles if item["is_assigned"]
            ]
            missing_roles = [
                item["role_label"] for item in responsibles if not item["is_assigned"]
            ]
            if assigned_labels:
                dat.current_responsibles_display = ", ".join(assigned_labels)
            else:
                dat.current_responsibles_display = ""
            dat.current_responsibles_missing = missing_roles

        if "application" in relation_field_names and dat_items:
            application_field = model._meta.get_field("application")
            attname = application_field.attname  # application_id
            related_model = application_field.remote_field.model
            application_ids = {
                getattr(dat, attname)
                for dat in dat_items
                if getattr(dat, attname) is not None
            }
            if application_ids:
                applications = related_model.objects.in_bulk(application_ids)
                cache_attr = f"_{application_field.name}_cache"
                for dat in dat_items:
                    app_id = getattr(dat, attname)
                    if app_id is not None:
                        setattr(dat, cache_attr, applications.get(app_id))
        return dat_items

    def get_columns(self):
        dat_items = self.get_dat_items()
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
                dat_items=dat_items,
            ),
            self._build_column(
                key="in_progress",
                states=in_progress_states,
                step_by_state=step_by_state,
                dat_items=dat_items,
            ),
            self._build_column(
                key="completed",
                states=completed_states,
                step_by_state=step_by_state,
                dat_items=dat_items,
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


class MyTasksBoardView(WorkflowBoardView):
    """Personal Kanban board focusing on the connected user's duties."""

    column_titles = {
        "blocked": "Bloquer",
        "in_progress": "En cours",
        "validation": "Validation",
    }

    column_descriptions = {
        "blocked": (
            "Au moins une autre personne doit agir avant que vous puissiez continuer sur ce DAT."
        ),
        "in_progress": (
            "Ces DAT attendent une action de votre part selon vos autorisations actuelles."
        ),
        "validation": (
            "Vous avez realise vos actions et attendez la finalisation par les autres intervenants."
        ),
    }

    def _step_has_user_write_access(self, step):
        user = self.request.user
        user_id = getattr(user, "id", None)
        role_id = getattr(getattr(user, "role", None), "id", None)
        if user_id is None and role_id is None:
            return False
        for permission in step.write_permissions.all():
            if permission.user_id == user_id:
                return True
            if role_id and permission.role_id == role_id:
                return True
        return False

    def get_columns(self):
        steps = list(self.workflow.steps.all())
        if not steps:
            return []

        step_indices = {step.state: index for index, step in enumerate(steps)}

        user_step_indices = [
            index for index, step in enumerate(steps) if self._step_has_user_write_access(step)
        ]
        user_step_indices.sort()
        user_step_index_set = set(user_step_indices)

        validation_statuses = {
            DATStatus.VALIDATION_FINALE,
            DATStatus.VALIDATION_RESERVE,
        }
        final_statuses = {
            DATStatus.DAT_REFUSE,
            DATStatus.DAT_VALIDE,
        }

        columns = {
            "blocked": [],
            "in_progress": [],
            "validation": [],
        }

        dat_items = self.get_dat_items()
        if not user_step_indices:
            # user has no assigned steps; return empty columns
            pass
        else:
            for dat in dat_items:
                current_index = step_indices.get(dat.status)
                if current_index is None:
                    continue

                if dat.status in final_statuses:
                    # Nothing to do once the DAT is accepted or refused.
                    continue

                has_future_assignment = any(idx > current_index for idx in user_step_indices)
                has_past_assignment = any(idx < current_index for idx in user_step_indices)
                is_current_step = current_index in user_step_index_set

                if not (has_future_assignment or has_past_assignment or is_current_step):
                    # Skip DAT items unrelated to the user's responsibilities.
                    continue

                if getattr(dat, "can_progress", False):
                    columns["in_progress"].append(dat)
                    continue

                next_status = getattr(dat, "next_status", None)
                if dat.status in validation_statuses or next_status in final_statuses:
                    columns["validation"].append(dat)
                    continue

                columns["blocked"].append(dat)

        ordered_keys = ["blocked", "in_progress", "validation"]
        return [
            {
                "key": key,
                "title": self.column_titles[key],
                "description": self.column_descriptions.get(key, ""),
                "status_codes": [],
                "status_labels": [],
                "items": columns.get(key, []),
                "read_permissions": [],
                "write_permissions": [],
            }
            for key in ordered_keys
        ]
