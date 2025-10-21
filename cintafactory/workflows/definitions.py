from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence, Tuple


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


# --- Default workflow definitions -------------------------------------------------

WORKFLOW_DEFINITIONS: Tuple[WorkflowDefinition, ...] = (
    WorkflowDefinition(
        code="dat-validation",
        name="Validation des DAT",
        model="dat.DAT",
        description=(
            "Processus de validation des dossiers d'architecture garantissant la conformité "
            "technique, la sécurité et l'approbation managériale."
        ),
        steps=(
            WorkflowStepDefinition(
                key="besoin-dal",
                name="Nouveau besoin (DAL)",
                status="besoin_dal",
                order=10,
                is_initial=True,
                description="Saisie de la demande initiale par le porteur du dossier.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("architect",)),
                    StepPermissionDefinition(
                        permission="read",
                        roles=("architect", "technical-reviewer", "security-officer", "director"),
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="nouveau-dossier",
                name="Nouveau dossier (DAT)",
                status="nouveau_dat",
                order=20,
                description="Création et complétion du dossier DAT.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("technical-reviewer",)),
                    StepPermissionDefinition(
                        permission="read",
                        roles=("architect", "technical-reviewer", "security-officer", "director"),
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="validation-referent",
                name="Validation du référent",
                status="validation_referent",
                order=30,
                description="Revue et validation par le référent architecte.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("technical-reviewer", "director")),
                    StepPermissionDefinition(
                        permission="read",
                        roles=("architect", "technical-reviewer", "security-officer", "director"),
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="instruction-urbanisme",
                name="Instruction urbanisme",
                status="instruction_urbanisme",
                order=40,
                description="Instruction par les équipes urbanisme.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("technical-reviewer",)),
                    StepPermissionDefinition(permission="read", roles=("architect", "technical-reviewer")),
                ),
            ),
            WorkflowStepDefinition(
                key="documentation-technique",
                name="Documentation architecture technique",
                status="documentation_technique",
                order=50,
                description="Production de la documentation technique consolidée.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("technical-reviewer",)),
                    StepPermissionDefinition(permission="read", roles=("architect", "technical-reviewer")),
                ),
            ),
            WorkflowStepDefinition(
                key="analyse-risque",
                name="Analyse de risque",
                status="analyse_risque",
                order=60,
                description="Analyse de risque cyber réalisée par la sécurité.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("security-officer",)),
                    StepPermissionDefinition(permission="read", roles=("technical-reviewer", "security-officer", "director")),
                ),
            ),
            WorkflowStepDefinition(
                key="preconisation-securite",
                name="Préconisation sécurité",
                status="preconisation_securite",
                order=70,
                description="Emission des recommandations sécurité.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("security-officer",)),
                    StepPermissionDefinition(permission="read", roles=("technical-reviewer", "security-officer", "director")),
                ),
            ),
            WorkflowStepDefinition(
                key="derogation-pssi",
                name="Dérogation PSSI",
                status="derogation_pssi",
                order=80,
                description="Gestion des dérogations au référentiel sécurité.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("security-officer",)),
                    StepPermissionDefinition(permission="read", roles=("technical-reviewer", "security-officer", "director")),
                ),
            ),
            WorkflowStepDefinition(
                key="architecture-prete",
                name="Architecture prête",
                status="architecture_prete",
                order=90,
                description="Architecture validée et prête à être déployée.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("technical-reviewer", "director")),
                    StepPermissionDefinition(permission="read", roles=("architect", "technical-reviewer", "security-officer", "director")),
                ),
            ),
            WorkflowStepDefinition(
                key="inscription-offres-service",
                name="Inscription offres de service",
                status="inscription_offres_service",
                order=100,
                description="Inscription dans les offres de service adaptées.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("director",)),
                    StepPermissionDefinition(permission="read", roles=("technical-reviewer", "director")),
                ),
            ),
            WorkflowStepDefinition(
                key="validation-capacitaire",
                name="Validation capacitaire",
                status="validation_capacitaire",
                order=110,
                description="Vérification des capacités d'hébergement et d'exploitation.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("director",)),
                    StepPermissionDefinition(permission="read", roles=("technical-reviewer", "director")),
                ),
            ),
            WorkflowStepDefinition(
                key="cartographie-flux",
                name="Cartographie des flux",
                status="cartographie_flux",
                order=120,
                description="Mise à jour de la cartographie des flux applicatifs.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("technical-reviewer",)),
                    StepPermissionDefinition(permission="read", roles=("technical-reviewer", "director")),
                ),
            ),
            WorkflowStepDefinition(
                key="validation-infrastructure",
                name="Validation infrastructure / exploitation",
                status="validation_infrastructure",
                order=130,
                description="Validation finale par l'infrastructure et l'exploitation.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("director",)),
                    StepPermissionDefinition(permission="read", roles=("technical-reviewer", "security-officer", "director")),
                ),
            ),
            WorkflowStepDefinition(
                key="dat-valide",
                name="DAT validé",
                status="dat_valide",
                order=140,
                description="Dossier DAT consolidé et prêt pour comité.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("director",)),
                    StepPermissionDefinition(permission="read", roles=("architect", "technical-reviewer", "security-officer", "director")),
                ),
            ),
            WorkflowStepDefinition(
                key="presentation-comite",
                name="Présentation en comité",
                status="presentation_comite",
                order=150,
                description="Présentation du dossier au comité de validation.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("director",)),
                    StepPermissionDefinition(permission="read", roles=("architect", "technical-reviewer", "security-officer", "director")),
                ),
            ),
            WorkflowStepDefinition(
                key="levee-reserve",
                name="Levée de réserve",
                status="levee_reserve",
                order=160,
                description="Traitement des réserves ou refus émis en comité.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("technical-reviewer", "security-officer")),
                    StepPermissionDefinition(permission="read", roles=("architect", "technical-reviewer", "security-officer", "director")),
                ),
            ),
            WorkflowStepDefinition(
                key="dat-publie",
                name="DAT publié",
                status="dat_publie",
                order=170,
                description="Publication finale du DAT et communication.",
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("director",)),
                    StepPermissionDefinition(permission="read", roles=("architect", "technical-reviewer", "security-officer", "director")),
                ),
            ),
        ),
    ),
)
