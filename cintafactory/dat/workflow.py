from __future__ import annotations

import logging
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from workflows.exceptions import WorkflowConfigurationError
from workflows.models import WorkflowInstance
from workflows.registry import register_workflow_adapter
from workflows.services import ensure_workflow_instance

from .models import DAT
from .permissions import user_is_dat_admin
from .sections import SECTION_STATUS_VALIDATED_VALUE


class DATWorkflowAdapter:
    """DAT-specific facts and effects behind generic workflow boundary."""

    guards = frozenset(
        {
            "always",
            "all_sections_validated",
            "sections_not_all_validated",
            "all_responsible_validated",
            "force_in_progress",
        }
    )
    actions = frozenset({"reset_section_statuses"})

    def initial_state(self, obj: Any, specification: dict) -> str:
        states = {step.get("status") for step in specification.get("steps", [])}
        explicit_state = getattr(obj, "_workflow_initial_state", None)
        if explicit_state in states:
            return str(explicit_state)
        legacy_state = getattr(obj, "status", None)
        if legacy_state in states:
            return str(legacy_state)
        for step in specification.get("steps", []):
            if step.get("is_initial"):
                return str(step["status"])
        raise WorkflowConfigurationError("DAT workflow has no initial state")

    def evaluate_guard(
        self,
        name: str,
        obj: Any,
        *,
        actor: Any = None,
        context: dict | None = None,
    ) -> bool:
        if name in {"", "always"}:
            return True
        status_map = self._status_map(obj, context)
        all_validated = self._all_sections_validated(status_map)
        if name == "all_sections_validated":
            return all_validated
        if name == "sections_not_all_validated":
            return not all_validated
        if name == "all_responsible_validated":
            return self._all_responsible_validated(status_map)
        if name == "force_in_progress":
            return bool((context or {}).get("force_in_progress"))
        raise WorkflowConfigurationError(f"Unknown DAT workflow guard '{name}'")

    def perform_action(
        self,
        name: str,
        obj: Any,
        *,
        actor: Any = None,
        context: dict | None = None,
    ) -> None:
        if not name:
            return
        if name != "reset_section_statuses":
            raise WorkflowConfigurationError(f"Unknown DAT workflow action '{name}'")
        from .views import build_section_status_map, reset_section_statuses_to_default

        status_map = (context or {}).get("status_map")
        status_choices = (context or {}).get("status_choices")
        if status_map is None or status_choices is None:
            status_map, status_choices = build_section_status_map(obj)
        reset_section_statuses_to_default(
            obj,
            status_map=status_map,
            status_choices=status_choices,
        )

    def actor_has_any_role(self, obj: Any, actor: Any, roles: tuple[str, ...]) -> bool:
        if actor is None or not getattr(actor, "is_authenticated", False):
            return False
        if user_is_dat_admin(actor):
            return True
        actor_id = getattr(actor, "pk", None)
        if actor_id is None:
            return False
        for participant in obj.participants.all():
            role = getattr(participant, "role", None)
            if participant.user_id == actor_id and getattr(role, "slug", None) in roles:
                return True
        return False

    def project_state(self, obj: Any, state: str, *, actor: Any = None) -> None:
        """Compatibility projection for code/data not migrated from DAT.status yet."""

        if getattr(obj, "status", None) == state:
            return
        if actor is not None:
            obj._history_actor = actor  # type: ignore[attr-defined]
        obj.status = state
        obj.save(update_fields=["status", "updated_at"])

    @staticmethod
    def _status_map(obj: Any, context: dict | None) -> dict[str, dict]:
        supplied = (context or {}).get("status_map")
        if isinstance(supplied, dict):
            return supplied
        from .views import build_section_status_map

        status_map, _choices = build_section_status_map(obj)
        return status_map

    @staticmethod
    def _all_sections_validated(status_map: dict[str, dict] | None) -> bool:
        if not status_map:
            return False
        for status_info in status_map.values():
            if status_info.get("has_status") and status_info.get("value") != SECTION_STATUS_VALIDATED_VALUE:
                return False
        return True

    @staticmethod
    def _all_responsible_validated(status_map: dict[str, dict] | None) -> bool:
        if not status_map:
            return False
        for status_info in status_map.values():
            if (
                status_info.get("has_status")
                and status_info.get("responsable_value") != SECTION_STATUS_VALIDATED_VALUE
            ):
                return False
        return True


logger = logging.getLogger(__name__)

register_workflow_adapter("dat.dat", DATWorkflowAdapter())


@receiver(post_save, sender=DAT, dispatch_uid="dat_create_workflow_instance")
def create_dat_workflow_instance(sender, instance: DAT, created: bool, **kwargs) -> None:
    if not created:
        return

    def _create() -> None:
        try:
            ensure_workflow_instance(instance)
        except WorkflowConfigurationError:
            logger.exception(
                "Unable to create DAT workflow instance",
                extra={"dat_id": str(instance.pk)},
            )

    transaction.on_commit(_create)


@receiver(post_delete, sender=DAT, dispatch_uid="dat_delete_workflow_instance")
def delete_dat_workflow_instance(sender, instance: DAT, **kwargs) -> None:
    content_type = ContentType.objects.get_for_model(DAT, for_concrete_model=False)
    WorkflowInstance.objects.filter(
        content_type=content_type,
        object_id=str(instance.pk),
    ).delete()
