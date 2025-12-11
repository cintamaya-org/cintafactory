from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence, Tuple

from dat.constants import (
    DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS,
    DAT_STATUS_REQUIRED_ROLES,
)


@dataclass(frozen=True)
class StepPermissionDefinition:
    """Declarative description of a single permission binding."""

    permission: str
    roles: Sequence[str] = field(default_factory=tuple)
    users: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class WorkflowStepDefinition:
    """Single column/step configuration for the Kanban board."""

    key: str
    name: str
    status: str
    description: str = ""
    order: int = 0
    is_initial: bool = False
    permissions: Sequence[StepPermissionDefinition] = field(default_factory=tuple)


@dataclass(frozen=True)
class WorkflowDefinition:
    """High-level workflow declaration bound to a Django model."""

    code: str
    name: str
    model: str
    description: str = ""
    steps: Sequence[WorkflowStepDefinition] = field(default_factory=tuple)


# --- Shared role helpers ---------------------------------------------------------

COMITE_VALIDATION_ROLE_SLUG = "comite-validation"
ALL_DAT_ROLES: Tuple[str, ...] = DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS
DAT_ROLES_WITHOUT_COMITE: Tuple[str, ...] = tuple(
    slug for slug in DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS if slug != COMITE_VALIDATION_ROLE_SLUG
)


def required_roles(status: str) -> Tuple[str, ...]:
    try:
        return DAT_STATUS_REQUIRED_ROLES[status]
    except KeyError as exc:
        raise KeyError(f"Unknown DAT status '{status}' in workflow definitions") from exc


# --- Default workflow definitions -------------------------------------------------

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
                description="Ouverture du dossier par le porteur de la demande.",
                permissions=(
                    StepPermissionDefinition(
                        permission="write",
                        roles=required_roles("nouvelle_demande"),
                    ),
                    StepPermissionDefinition(
                        permission="read",
                        roles=ALL_DAT_ROLES,
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="en-cours",
                name="En cours",
                status="en_cours",
                order=20,
                description="Saisie et complétion des sections avant revue.",
                permissions=(
                    StepPermissionDefinition(
                        permission="write",
                        roles=required_roles("en_cours"),
                    ),
                    StepPermissionDefinition(
                        permission="read",
                        roles=ALL_DAT_ROLES,
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="en-attente-revue",
                name="En attente de revue",
                status="en_attente_de_revue",
                order=30,
                description="Toutes les sections sont validées, décision attendue.",
                permissions=(
                    StepPermissionDefinition(
                        permission="write",
                        roles=required_roles("en_attente_de_revue"),
                    ),
                    StepPermissionDefinition(
                        permission="read",
                        roles=ALL_DAT_ROLES,
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="reserve",
                name="Réserve",
                status="reserve",
                order=40,
                description="Réserve émise : corrections attendues avant une nouvelle revue.",
                permissions=(
                    StepPermissionDefinition(
                        permission="write",
                        roles=required_roles("reserve"),
                    ),
                    StepPermissionDefinition(
                        permission="read",
                        roles=ALL_DAT_ROLES,
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="valide",
                name="Valider",
                status="valider",
                order=50,
                description="DAT validé et clôturé.",
                permissions=(
                    StepPermissionDefinition(
                        permission="read",
                        roles=ALL_DAT_ROLES,
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="refuse",
                name="Refusé",
                status="refuse",
                order=60,
                description="DAT refusé et clôturé.",
                permissions=(
                    StepPermissionDefinition(
                        permission="read",
                        roles=ALL_DAT_ROLES,
                    ),
                ),
            ),
        ),
    ),
)
