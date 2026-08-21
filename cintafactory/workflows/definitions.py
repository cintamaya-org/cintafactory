from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Sequence, Tuple


@dataclass(frozen=True)
class StepPermissionDefinition:
    """Declarative permission binding used by boards and task assignment."""

    permission: str
    roles: Sequence[str] = field(default_factory=tuple)
    users: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class WorkflowStepDefinition:
    """State metadata exposed through workflow API."""

    key: str
    name: str
    status: str
    description: str = ""
    order: int = 0
    is_initial: bool = False
    lane: str = "in_progress"
    capabilities: Sequence[str] = field(default_factory=tuple)
    permissions: Sequence[StepPermissionDefinition] = field(default_factory=tuple)


@dataclass(frozen=True)
class WorkflowTransitionDefinition:
    """Event-driven transition between workflow states.

    Guards and actions are symbolic names implemented by target model adapter.
    Workflow configuration never contains executable code.
    """

    event: str
    sources: Sequence[str]
    target: str
    guard: str = "always"
    action: str = ""
    roles: Sequence[str] = field(default_factory=tuple)
    automatic: bool = False
    order: int = 0


@dataclass(frozen=True)
class WorkflowDefinition:
    """Versionable workflow contract bound to a Django model."""

    code: str
    name: str
    model: str
    description: str = ""
    steps: Sequence[WorkflowStepDefinition] = field(default_factory=tuple)
    transitions: Sequence[WorkflowTransitionDefinition] = field(default_factory=tuple)
    visualization: dict[str, Any] = field(default_factory=dict)


def definition_to_spec(definition: WorkflowDefinition) -> dict[str, Any]:
    """Return stable JSON-compatible representation persisted as immutable version."""

    return asdict(definition)


# Role slugs live in workflow contract. Workflow engine does not import DAT code.
ALL_DAT_ROLES: Tuple[str, ...] = (
    "porteur-demande",
    "architecte-referent",
    "architecte-technique",
    "urbaniste",
    "analyste-secu",
    "rssi",
    "comite-validation",
    "infra-exploitation",
)

DAT_STATE_ROLES: dict[str, Tuple[str, ...]] = {
    "nouvelle_demande": ("porteur-demande",),
    "en_cours": ("porteur-demande",),
    "en_attente_de_revue": ("architecte-referent", "comite-validation"),
    "reserve": ("architecte-referent", "porteur-demande"),
    "valider": ("architecte-referent",),
    "refuse": ("architecte-referent",),
}

DAT_WORKFLOW_VISUALIZATION: dict[str, Any] = {
    "layout": {"height": 720, "padding": 44},
    "nodes": [
        {
            "id": "urbanisme",
            "title": "Urbanisme",
            "content": "",
            "variant": "mid",
            "row": 0,
            "col": 0,
            "links": ["validation"],
            "scope": "section",
            "section": "urbanisme",
        },
        {
            "id": "architecture-technique",
            "title": "Architecture Technique",
            "content": "",
            "variant": "mid",
            "row": 1,
            "col": 0,
            "links": ["validation"],
            "scope": "section",
            "section": "architecture",
        },
        {
            "id": "cybersecurite",
            "title": "Cybersecurite",
            "content": "",
            "variant": "start",
            "row": 2,
            "col": 0,
            "links": ["validation"],
            "scope": "section",
            "section": "cybersecurite",
        },
        {
            "id": "exploitation",
            "title": "Exploitation",
            "content": "",
            "variant": "mid",
            "row": 3,
            "col": 0,
            "links": ["validation"],
            "scope": "section",
            "section": "exploitation",
        },
        {
            "id": "validation",
            "title": "Validation",
            "content": "DAT {{ dat.reference }}",
            "variant": "mid",
            "row": 2,
            "col": 2,
            "links": [],
            "scope": "workflow",
        },
    ],
}


def _permissions(state: str, *, writable: bool = True) -> tuple[StepPermissionDefinition, ...]:
    values: list[StepPermissionDefinition] = []
    if writable:
        values.append(StepPermissionDefinition(permission="write", roles=DAT_STATE_ROLES[state]))
    values.append(StepPermissionDefinition(permission="read", roles=ALL_DAT_ROLES))
    return tuple(values)


WORKFLOW_DEFINITIONS: Tuple[WorkflowDefinition, ...] = (
    WorkflowDefinition(
        code="dat-validation",
        name="Validation des DAT",
        model="dat.DAT",
        description=(
            "Processus simplifie de validation des dossiers d'architecture. "
            "Le porteur prépare le dossier, l'équipe de revue tranche (validation, refus ou réserve)."
        ),
        steps=(
            WorkflowStepDefinition(
                key="nouvelle-demande",
                name="Nouvelle demande",
                status="nouvelle_demande",
                order=10,
                is_initial=True,
                lane="initial",
                capabilities=("editable", "owner_editable"),
                description="Ouverture du dossier par le porteur de la demande.",
                permissions=_permissions("nouvelle_demande"),
            ),
            WorkflowStepDefinition(
                key="en-cours",
                name="En cours",
                status="en_cours",
                order=20,
                lane="in_progress",
                capabilities=("editable", "owner_editable"),
                description="Saisie et complétion des sections avant revue.",
                permissions=_permissions("en_cours"),
            ),
            WorkflowStepDefinition(
                key="en-attente-revue",
                name="En attente de revue",
                status="en_attente_de_revue",
                order=30,
                lane="in_progress",
                capabilities=("editable", "reviewable"),
                description="Toutes les sections sont validées, décision attendue.",
                permissions=_permissions("en_attente_de_revue"),
            ),
            WorkflowStepDefinition(
                key="reserve",
                name="Réserve",
                status="reserve",
                order=40,
                lane="in_progress",
                capabilities=("editable", "owner_editable", "requires_corrections"),
                description="Réserve émise : corrections attendues avant une nouvelle revue.",
                permissions=_permissions("reserve"),
            ),
            WorkflowStepDefinition(
                key="valide",
                name="Valider",
                status="valider",
                order=50,
                lane="completed",
                capabilities=("terminal", "approved"),
                description="DAT validé et clôturé.",
                permissions=_permissions("valider", writable=False),
            ),
            WorkflowStepDefinition(
                key="refuse",
                name="Refusé",
                status="refuse",
                order=60,
                lane="completed",
                capabilities=("terminal", "rejected"),
                description="DAT refusé et clôturé.",
                permissions=_permissions("refuse", writable=False),
            ),
        ),
        transitions=(
            # Priority preserves former refresh_dat_status() semantics.
            WorkflowTransitionDefinition(
                event="sections_changed",
                sources=("nouvelle_demande", "en_cours", "en_attente_de_revue", "reserve"),
                target="valider",
                guard="all_responsible_validated",
                automatic=True,
                order=10,
            ),
            WorkflowTransitionDefinition(
                event="sections_changed",
                sources=("reserve",),
                target="en_attente_de_revue",
                guard="all_sections_validated",
                automatic=True,
                order=20,
            ),
            WorkflowTransitionDefinition(
                event="sections_changed",
                sources=("nouvelle_demande", "en_cours"),
                target="en_attente_de_revue",
                guard="all_sections_validated",
                automatic=True,
                order=30,
            ),
            WorkflowTransitionDefinition(
                event="sections_changed",
                sources=("en_attente_de_revue",),
                target="en_cours",
                guard="sections_not_all_validated",
                automatic=True,
                order=40,
            ),
            WorkflowTransitionDefinition(
                event="sections_changed",
                sources=("nouvelle_demande",),
                target="en_cours",
                guard="force_in_progress",
                automatic=True,
                order=50,
            ),
            WorkflowTransitionDefinition(
                event="approve",
                sources=("en_attente_de_revue",),
                target="valider",
                roles=("architecte-referent", "comite-validation"),
                order=10,
            ),
            WorkflowTransitionDefinition(
                event="reject",
                sources=("en_attente_de_revue",),
                target="refuse",
                roles=("architecte-referent", "comite-validation"),
                order=20,
            ),
            WorkflowTransitionDefinition(
                event="request_changes",
                sources=("en_attente_de_revue",),
                target="reserve",
                action="reset_section_statuses",
                roles=("architecte-referent", "comite-validation"),
                order=30,
            ),
        ),
        visualization=DAT_WORKFLOW_VISUALIZATION,
    ),
)
