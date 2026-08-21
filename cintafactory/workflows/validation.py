from __future__ import annotations

from collections import defaultdict, deque

from .definitions import WorkflowDefinition
from .exceptions import WorkflowConfigurationError


ALLOWED_PERMISSION_TYPES = {"read", "write"}
ALLOWED_LANES = {"initial", "in_progress", "completed"}


def validate_workflow_definition(definition: WorkflowDefinition) -> None:
    """Reject structurally unsafe definitions before publishing a version."""

    errors: list[str] = []
    if not definition.code:
        errors.append("workflow code is required")
    if not definition.model or "." not in definition.model:
        errors.append("model must use 'app_label.ModelName' format")

    states = [step.status for step in definition.steps]
    state_set = set(states)
    if not states:
        errors.append("at least one state is required")
    if len(states) != len(state_set):
        errors.append("state codes must be unique")

    step_keys = [step.key for step in definition.steps]
    if len(step_keys) != len(set(step_keys)):
        errors.append("step keys must be unique")

    initials = [step.status for step in definition.steps if step.is_initial]
    if len(initials) != 1:
        errors.append("exactly one initial state is required")

    for step in definition.steps:
        if step.lane not in ALLOWED_LANES:
            errors.append(f"state '{step.status}' has invalid lane '{step.lane}'")
        for permission in step.permissions:
            if permission.permission not in ALLOWED_PERMISSION_TYPES:
                errors.append(
                    f"state '{step.status}' has invalid permission '{permission.permission}'"
                )
            if not permission.roles and not permission.users:
                errors.append(f"state '{step.status}' has permission without subjects")

    seen_transitions: set[tuple[str, tuple[str, ...], str, str, int]] = set()
    transition_slots: set[tuple[str, str, int]] = set()
    adjacency: dict[str, set[str]] = defaultdict(set)
    for transition in definition.transitions:
        if not transition.event:
            errors.append("transition event is required")
        if not transition.sources:
            errors.append(f"transition '{transition.event}' requires a source")
        for source in transition.sources:
            if source not in state_set:
                errors.append(f"transition '{transition.event}' has unknown source '{source}'")
            else:
                adjacency[source].add(transition.target)
        if transition.target not in state_set:
            errors.append(
                f"transition '{transition.event}' has unknown target '{transition.target}'"
            )
        identity = (
            transition.event,
            tuple(transition.sources),
            transition.target,
            transition.guard,
            transition.order,
        )
        if identity in seen_transitions:
            errors.append(f"duplicate transition '{transition.event}' at order {transition.order}")
        seen_transitions.add(identity)
        for source in transition.sources:
            slot = (transition.event, source, transition.order)
            if slot in transition_slots:
                errors.append(
                    f"ambiguous transition '{transition.event}' from '{source}' "
                    f"at order {transition.order}"
                )
            transition_slots.add(slot)

    visualization = definition.visualization or {}
    nodes = visualization.get("nodes", []) if isinstance(visualization, dict) else []
    if not isinstance(nodes, list):
        errors.append("visualization nodes must be a list")
        nodes = []
    node_ids = {
        str(node.get("id"))
        for node in nodes
        if isinstance(node, dict) and node.get("id")
    }
    if len(node_ids) != len(nodes):
        errors.append("visualization node IDs must be present and unique")
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        if node.get("scope") == "section" and not node.get("section"):
            errors.append(f"visualization node '{node_id}' requires a section key")
        for target in node.get("links") or ():
            if target not in node_ids:
                errors.append(
                    f"visualization node '{node_id}' links to unknown node '{target}'"
                )

    if len(initials) == 1:
        reachable = _reachable_states(initials[0], adjacency)
        unreachable = state_set - reachable
        for state in sorted(unreachable):
            errors.append(f"state '{state}' is unreachable from initial state")

    if errors:
        joined = "; ".join(errors)
        raise WorkflowConfigurationError(f"Invalid workflow '{definition.code}': {joined}")


def _reachable_states(initial: str, adjacency: dict[str, set[str]]) -> set[str]:
    seen = {initial}
    queue = deque([initial])
    while queue:
        source = queue.popleft()
        for target in adjacency.get(source, ()):
            if target in seen:
                continue
            seen.add(target)
            queue.append(target)
    return seen
