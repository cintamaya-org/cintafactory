from __future__ import annotations

from typing import Any, Protocol

from .exceptions import WorkflowConfigurationError


class WorkflowAdapter(Protocol):
    """Stable boundary between generic workflow engine and business domain."""

    def initial_state(self, obj: Any, specification: dict) -> str: ...

    def evaluate_guard(
        self,
        name: str,
        obj: Any,
        *,
        actor: Any = None,
        context: dict | None = None,
    ) -> bool: ...

    def perform_action(
        self,
        name: str,
        obj: Any,
        *,
        actor: Any = None,
        context: dict | None = None,
    ) -> None: ...

    def actor_has_any_role(self, obj: Any, actor: Any, roles: tuple[str, ...]) -> bool: ...

    def project_state(self, obj: Any, state: str, *, actor: Any = None) -> None: ...


_adapters: dict[str, WorkflowAdapter] = {}


def register_workflow_adapter(model_label: str, adapter: WorkflowAdapter) -> None:
    _adapters[model_label.lower()] = adapter


def get_workflow_adapter(obj_or_label: Any) -> WorkflowAdapter:
    if isinstance(obj_or_label, str):
        label = obj_or_label.lower()
    else:
        label = obj_or_label._meta.label_lower
    try:
        return _adapters[label]
    except KeyError as exc:
        raise WorkflowConfigurationError(
            f"No workflow adapter registered for model '{label}'"
        ) from exc

