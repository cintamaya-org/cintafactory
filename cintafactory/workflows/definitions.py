from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence, Tuple


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
            "Processus de validation des dossiers d'architecture garantissant la conformite "
            "technique, la securite et l'approbation manageriale."
        ),
        steps=(
            WorkflowStepDefinition(
                key="demande-initiale",
                name="Demande initiale",
                status="demande_initiale",
                order=10,
                is_initial=True,
                description=(
                    "Ouverture du dossier (nouvelle application ou evolution) par le porteur de la "
                    "demande avec reprise automatique des informations applicatives connues."
                ),
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("porteur-demande",)),
                    StepPermissionDefinition(
                        permission="read",
                        roles=(
                            "porteur-demande",
                            "architecte-referent",
                            "architecte-technique",
                            "urbaniste",
                            "analyste-secu",
                            "rssi",
                            "infra-exploitation",
                            "comite-validation",
                        ),
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="validation-referent",
                name="Validation du referent",
                status="validation_referent",
                order=20,
                description=(
                    "Le referent architecture verifie la completude de la demande et affecte un "
                    "architecte technique (validation ou renvoi au porteur avec commentaire)."
                ),
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("architecte-referent",)),
                    StepPermissionDefinition(
                        permission="read",
                        roles=(
                            "porteur-demande",
                            "architecte-referent",
                            "architecte-technique",
                            "urbaniste",
                            "analyste-secu",
                            "rssi",
                            "infra-exploitation",
                            "comite-validation",
                        ),
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="instruction-architecture",
                name="Instruction architecture technique",
                status="instruction_architecture",
                order=30,
                description=(
                    "L'architecte technique met a jour le DAT, produit le schema cible et formalise les "
                    "arbitrages demandes avant passage a la securite."
                ),
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("architecte-technique",)),
                    StepPermissionDefinition(
                        permission="read",
                        roles=(
                            "porteur-demande",
                            "architecte-referent",
                            "architecte-technique",
                            "urbaniste",
                            "analyste-secu",
                            "rssi",
                            "infra-exploitation",
                        ),
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="instruction-urbanisme",
                name="Instruction urbanisme",
                status="instruction_urbanisme",
                order=40,
                description=(
                    "Mise a jour du schema d'urbanisme et controle de conformite aux standards par "
                    "l'urbaniste en parallele de l'instruction technique."
                ),
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("urbaniste",)),
                    StepPermissionDefinition(
                        permission="read",
                        roles=(
                            "porteur-demande",
                            "architecte-referent",
                            "architecte-technique",
                            "urbaniste",
                            "analyste-secu",
                            "rssi",
                            "infra-exploitation",
                        ),
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="analyse-securite",
                name="Analyse cyber securite",
                status="analyse_securite",
                order=50,
                description=(
                    "L'analyste securite conduit les ateliers de risque, formalise les preconisations et "
                    "notifie le porteur ainsi que l'architecte technique. Les refus declenchent la "
                    "demande de derogation."
                ),
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("analyste-secu",)),
                    StepPermissionDefinition(
                        permission="read",
                        roles=(
                            "porteur-demande",
                            "architecte-referent",
                            "architecte-technique",
                            "urbaniste",
                            "analyste-secu",
                            "rssi",
                            "infra-exploitation",
                        ),
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="generation-cartographie",
                name="Generation cartographie et inventaire",
                status="generation_cartographie",
                order=60,
                description=(
                    "Synchronisation automatique des schemas techniques vers la cartographie des flux et "
                    "mise a jour de l'inventaire (assets, capacites, consommations)."
                ),
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("architecte-technique",)),
                    StepPermissionDefinition(
                        permission="read",
                        roles=(
                            "porteur-demande",
                            "architecte-referent",
                            "architecte-technique",
                            "urbaniste",
                            "analyste-secu",
                            "rssi",
                            "infra-exploitation",
                        ),
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="revue-infra-exploitation",
                name="Revue infra / exploitation",
                status="revue_infra_exploitation",
                order=70,
                description=(
                    "Validation capacitaire, rattachement aux offres de service et evaluation budgetaire "
                    "par l'equipe infra / exploitation."
                ),
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("infra-exploitation",)),
                    StepPermissionDefinition(
                        permission="read",
                        roles=(
                            "porteur-demande",
                            "architecte-referent",
                            "architecte-technique",
                            "urbaniste",
                            "analyste-secu",
                            "rssi",
                            "infra-exploitation",
                        ),
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="validation-finale",
                name="Validation finale pluridisciplinaire",
                status="validation_finale",
                order=80,
                description=(
                    "Validation du DAT par les referents architecture technique, urbanisme, securite et "
                    "infra/exploitation avec suivi des commentaires."
                ),
                permissions=(
                    StepPermissionDefinition(
                        permission="write",
                        roles=(
                            "architecte-referent",
                            "urbaniste",
                            "rssi",
                            "infra-exploitation",
                        ),
                    ),
                    StepPermissionDefinition(
                        permission="read",
                        roles=(
                            "porteur-demande",
                            "architecte-referent",
                            "architecte-technique",
                            "urbaniste",
                            "analyste-secu",
                            "rssi",
                            "infra-exploitation",
                            "comite-validation",
                        ),
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="validation-reserve",
                name="Validation avec reserve",
                status="validation_reserve",
                order=90,
                description=(
                    "Suivi des reserves, attribution d'un responsable pour leur resolution et verification "
                    "de la levee avant applicabilite du DAT."
                ),
                permissions=(
                    StepPermissionDefinition(
                        permission="write",
                        roles=(
                            "architecte-technique",
                            "architecte-referent",
                            "urbaniste",
                            "analyste-secu",
                            "rssi",
                            "infra-exploitation",
                        ),
                    ),
                    StepPermissionDefinition(
                        permission="read",
                        roles=(
                            "porteur-demande",
                            "architecte-referent",
                            "architecte-technique",
                            "urbaniste",
                            "analyste-secu",
                            "rssi",
                            "infra-exploitation",
                            "comite-validation",
                        ),
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="dat-refuse",
                name="DAT refuse",
                status="dat_refuse",
                order=100,
                description=(
                    "Le dossier est refuse ou rejete : la version precedente reste applicable et le nouvel "
                    "etat est archive."
                ),
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("architecte-referent",)),
                    StepPermissionDefinition(
                        permission="read",
                        roles=(
                            "porteur-demande",
                            "architecte-referent",
                            "architecte-technique",
                            "urbaniste",
                            "analyste-secu",
                            "rssi",
                            "infra-exploitation",
                            "comite-validation",
                        ),
                    ),
                ),
            ),
            WorkflowStepDefinition(
                key="dat-valide",
                name="DAT valide",
                status="dat_valide",
                order=110,
                description=(
                    "Tous les avis sont poses : le DAT est valide, les reserves sont levees et les "
                    "intervenants sont notifies."
                ),
                permissions=(
                    StepPermissionDefinition(permission="write", roles=("architecte-referent",)),
                    StepPermissionDefinition(
                        permission="read",
                        roles=(
                            "porteur-demande",
                            "architecte-referent",
                            "architecte-technique",
                            "urbaniste",
                            "analyste-secu",
                            "rssi",
                            "infra-exploitation",
                            "comite-validation",
                        ),
                    ),
                ),
            ),
        ),
    ),
)
