from __future__ import annotations

import json
import copy
from typing import Any, Dict, Iterable, Tuple, Optional

from django.db import transaction

PLACEHOLDER_SUBSECTION_COUNT = 3


def _build_placeholder_parts(section_slug: str) -> Tuple[Dict[str, Any], ...]:
    """
    Provide default sub-sections so that each section is ready to be refined later.
    """
    parts: list[Dict[str, Any]] = []
    for index in range(1, PLACEHOLDER_SUBSECTION_COUNT + 1):
        parts.append(
            {
                "slug": f"{section_slug}-placeholder-{index}",
                "title": f"Sous-section {index}",
                "description": (
                    "Personnalisez cette sous-section en mettant à jour DEFAULT_DAT_SECTION_DEFINITIONS "
                    "et en ajoutant vos champs (entries)."
                ),
                "entries": (),
            }
        )
    return tuple(parts)


def _normalise_parts(section_slug: str, raw_parts: Iterable[Dict[str, Any]] | None) -> Tuple[Dict[str, Any], ...]:
    if not raw_parts:
        return _build_placeholder_parts(section_slug)
    normalised_parts: list[Dict[str, Any]] = []
    for part in raw_parts:
        normalised_part = {
            "slug": part["slug"],
            "title": part.get("title", part["slug"].replace("-", " ").title()),
            "description": part.get("description", ""),
            "entries": tuple(part.get("entries", ())),
        }
        normalised_parts.append(normalised_part)
    return tuple(normalised_parts)


DRAWIO_DIAGRAM_COLUMNS: Tuple[Dict[str, Any], ...] = (
    {"key": "nom_schema", "label": "Nom du schéma", "type": "text"},
    {
        "key": "diagramme_id",
        "label": "Diagramme Draw.io",
        "type": "text",
        "placeholder": "ID du diagramme (ex: 42)",
        "render": "drawio_diagram",
        "drawio": True,
        "drawio_name_key": "nom_schema",
        "button_label": "Éditer",
    },
    {
        "key": "description",
        "label": "Description",
        "type": "textarea",
        "rows": 3,
        "minHeight": 140,
    },
)


def _build_drawio_repeater_entry(key: str, label: str, *, allow_import: bool = True) -> Dict[str, Any]:
    columns = [copy.deepcopy(column) for column in DRAWIO_DIAGRAM_COLUMNS]
    if not allow_import:
        for column in columns:
            if column.get("key") == "diagramme_id":
                column["drawio_allow_import"] = False
                break
    return {
        "key": key,
        "label": label,
        "type": "repeater",
        "config": {"columns": columns},
    }


SECTION_BLUEPRINTS: Tuple[Dict[str, Any], ...] = (
    {
        "slug": "informations-generales",
        "title": "INFORMATIONS GÉNÉRALES",
        "description": "Informations de référence partagées avec l'ensemble des acteurs.",
        "allowed_roles": ["porteur-demande", "architecte-referent"],
        "parts": (
            {
                "slug": "informations-administratives",
                "title": "Informations Administratives",
                "entries": (
                    {
                        "key": "nom_projet",
                        "label": "Nom du projet",
                        "type": "long_text",
                        "config": {"rows": 4},
                    },
                    {
                        "key": "historique_versions",
                        "label": "Historique des versions du document",
                        "type": "repeater",
                        "config": {
                            "help_text": "Ajoutez une ligne par version validée du document (format JJ/MM/AA).",
                            "columns": [
                                {"key": "version", "label": "Version", "type": "text", "placeholder": "V1, V2…"},
                                {"key": "date_validation", "label": "Date de validation", "type": "date"},
                                {
                                    "key": "responsable",
                                    "label": "Responsable",
                                    "type": "text",
                                    "placeholder": "Nom Prénom (utilisateur référentiel)",
                                },
                            ],
                        },
                    },
                ),
            },
            {
                "slug": "description-solution",
                "title": "Description de la solution",
                "entries": (
                    {
                        "key": "raison_etre",
                        "label": "Raison d’être de la solution",
                        "type": "long_text",
                        "config": {"rows": 6},
                    },
                    {
                        "key": "typologie",
                        "label": "Typologie",
                        "type": "long_text",
                        "config": {
                            "rows": 4,
                            "help_text": "Application web, mobile, batch, API, plateforme Data…",
                        },
                    },
                    {
                        "key": "analyse_dict",
                        "label": "Analyse DICT",
                        "type": "repeater",
                        "config": {
                            "help_text": "Saisir les notes (1 à 4) pour D, I, C, T.",
                            "min_rows": 1,
                            "max_rows": 1,
                            "allow_row_addition": False,
                            "allow_row_removal": False,
                            "columns": [
                                {
                                    "key": "d",
                                    "label": "D",
                                    "type": "select",
                                    "choices": [
                                        {"value": 1, "label": "1"},
                                        {"value": 2, "label": "2"},
                                        {"value": 3, "label": "3"},
                                        {"value": 4, "label": "4"},
                                    ],
                                },
                                {
                                    "key": "i",
                                    "label": "I",
                                    "type": "select",
                                    "choices": [
                                        {"value": 1, "label": "1"},
                                        {"value": 2, "label": "2"},
                                        {"value": 3, "label": "3"},
                                        {"value": 4, "label": "4"},
                                    ],
                                },
                                {
                                    "key": "c",
                                    "label": "C",
                                    "type": "select",
                                    "choices": [
                                        {"value": 1, "label": "1"},
                                        {"value": 2, "label": "2"},
                                        {"value": 3, "label": "3"},
                                        {"value": 4, "label": "4"},
                                    ],
                                },
                                {
                                    "key": "t",
                                    "label": "T",
                                    "type": "select",
                                    "choices": [
                                        {"value": 1, "label": "1"},
                                        {"value": 2, "label": "2"},
                                        {"value": 3, "label": "3"},
                                        {"value": 4, "label": "4"},
                                    ],
                                },
                            ],
                        },
                    },
                ),
            },
        ),
    },
    {
        "slug": "besoins",
        "title": "BESOIN(S)",
        "description": "Capture des besoins exprimés par le porteur.",
        "allowed_roles": ["porteur-demande"],
        "parts": (
            {
                "slug": "typologie-besoin",
                "title": "Typologie de Besoin",
                "entries": (
                    {
                        "key": "typologie_besoin",
                        "label": "Décrire le type de besoin",
                        "type": "text",
                        "config": {
                            "help_text": "Précisez s'il s'agit d'une nouvelle application ou d'une modification (un seul choix possible).",
                            "widget": "radio",
                            "choices": [
                                {"value": "nouvelle_app", "label": "Nouvelle application"},
                                {
                                    "value": "modification_mineure",
                                    "label": "Modification mineure d'une application existante (ajout d'un flux, petite modification d'un composant)",
                                },
                                {
                                    "value": "evolution_majeure",
                                    "label": "Évolution majeure d'une application existante (modification complète du socle technique, ajout de fonctionnalité majeure)",
                                },
                            ],
                        },
                    },
                ),
            },
            {
                "slug": "detail-besoin",
                "title": "Détail du Besoin",
                "entries": (
                    {
                        "key": "besoin_creation",
                        "label": "Besoin de création",
                        "type": "long_text",
                        "config": {"rows": 6, "help_text": "Description libre du besoin de création."},
                    },
                    {
                        "key": "besoin_modification",
                        "label": "Besoin de modification",
                        "type": "long_text",
                        "config": {"rows": 6, "help_text": "Description libre du besoin de modification."},
                    },
                ),
            },
        ),
    },
    {
        "slug": "urbanisme",
        "title": "URBANISME",
        "description": "Analyse urbanisme et cohérence d'ensemble.",
        "allowed_roles": ["urbaniste"],
        "parts": (
            {
                "slug": "mapping-urbanisation-si",
                "title": "Mapping dans l’urbanisation du SI",
                "entries": (
                    {
                        "key": "domaine_metier_concerne",
                        "label": "Domaine métier concerné",
                        "type": "long_text",
                        "config": {"rows": 6, "help_text": "Description narrative du domaine métier impacté."},
                    },
                    {
                        "key": "sous_domaines_impactes",
                        "label": "Sous-domaines impactés",
                        "type": "long_text",
                        "config": {"rows": 6, "help_text": "Liste ou description des sous-domaines touchés."},
                    },
                    _build_drawio_repeater_entry("cartographie", "Cartographie", allow_import=False),
                ),
            },
            {
                "slug": "tableau-des-flux",
                "title": "Tableau des flux",
                "entries": (
                    {
                        "key": "flux_urbanisme",
                        "label": "Tableau des flux",
                        "type": "repeater",
                        "config": {
                            "columns": [
                                {
                                    "key": "statut",
                                    "label": "Statut",
                                    "type": "select",
                                    "choices": [
                                        {"value": "propose", "label": "Proposé"},
                                        {"value": "valide", "label": "Validé"},
                                        {"value": "deprecie", "label": "Déprécié"},
                                    ],
                                },
                                {"key": "flux_id", "label": "ID", "type": "text"},
                                {"key": "source", "label": "Source", "type": "text"},
                                {"key": "cible", "label": "Cible", "type": "text"},
                                {
                                    "key": "protocole",
                                    "label": "Protocole",
                                    "type": "text",
                                    "placeholder": "TCP, UDP, HTTP, etc.",
                                },
                                {"key": "port", "label": "Port", "type": "text"},
                                {
                                    "key": "chiffrement",
                                    "label": "Chiffrement",
                                    "type": "select",
                                    "choices": [
                                        {"value": "oui", "label": "Oui"},
                                        {"value": "non", "label": "Non"},
                                    ],
                                },
                                {
                                    "key": "authentification",
                                    "label": "Authentification",
                                    "type": "select",
                                    "choices": [
                                        {"value": "oui", "label": "Oui"},
                                        {"value": "non", "label": "Non"},
                                    ],
                                },
                            ]
                        },
                    },
                ),
            },
            {
                "slug": "conformite-urbanisme",
                "title": "Conformité Urbanisme",
                "entries": (
                    {
                        "key": "respect_principes_architecture",
                        "label": "Respect des principes d’architecture",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                    {
                        "key": "ecart_principes_architecture",
                        "label": "Écart avec les principes d’architecture",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                    {
                        "key": "pattern_utilise",
                        "label": "Pattern utilisé (microservices, CQRS, event-driven, etc.)",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                    {
                        "key": "usage_brique_transverse",
                        "label": "Usage de brique SI transverse (ESB, IAM, etc.)",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                ),
            },
            {
                "slug": "impact-si-existant",
                "title": "Impact sur le SI existant",
                "entries": (
                    {
                        "key": "evolution_ou_remplacement",
                        "label": "Évolution ou remplacement d’application existante",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                    {
                        "key": "nouvelles_interfaces",
                        "label": "Nouvelles interfaces",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                ),
            },
        ),
    },
    {
        "slug": "architecture",
        "title": "ARCHITECTURE",
        "description": "Vue d'architecture cible et décisions associées.",
        "allowed_roles": ["architecte-technique", "architecte-referent"],
        "parts": (
            {
                "slug": "presentation-generale",
                "title": "Présentation Générale",
                "entries": (
                    {
                        "key": "presentation_generale",
                        "label": "Présentation générale",
                        "type": "long_text",
                        "config": {"rows": 24},
                    },
                ),
            },
            {
                "slug": "hebergement-environnements",
                "title": "Hébergement & Environnements",
                "entries": (
                    {
                        "key": "hebergements",
                        "label": "Hébergements",
                        "type": "repeater",
                        "config": {
                            "columns": [
                                {
                                    "key": "environnement",
                                    "label": "Environnement",
                                    "type": "select",
                                    "choices": [
                                        {"value": "production", "label": "Production"},
                                        {"value": "preproduction", "label": "Préproduction"},
                                        {"value": "recette", "label": "Recette"},
                                        {"value": "integration", "label": "Intégration"},
                                        {"value": "developpement", "label": "Développement"},
                                        {"value": "autre", "label": "Autre"},
                                    ],
                                },
                                {
                                    "key": "type_hebergement",
                                    "label": "Type",
                                    "type": "select",
                                    "choices": [
                                        {"value": "on_premise", "label": "On-premises"},
                                        {"value": "cloud", "label": "Cloud"},
                                        {"value": "hybride", "label": "Hybride"},
                                        {"value": "autre", "label": "Autre"},
                                    ],
                                },
                                {
                                    "key": "localisation",
                                    "label": "Localisation",
                                    "type": "text",
                                    "placeholder": "Datacenter, région cloud, etc.",
                                },
                            ]
                        },
                    },
                    {
                        "key": "hebergement_commentaires",
                        "label": "Commentaires sur l'hébergement",
                        "type": "long_text",
                        "config": {"rows": 12},
                    },
                ),
            },
            {
                "slug": "solutions-utilisees",
                "title": "Solutions Utilisées",
                "entries": (
                    {
                        "key": "solutions",
                        "label": "Solutions",
                        "type": "repeater",
                        "config": {
                            "columns": [
                                {
                                    "key": "environnement",
                                    "label": "Environnement",
                                    "type": "select",
                                    "choices": [
                                        {"value": "production", "label": "Production"},
                                        {"value": "preproduction", "label": "Préproduction"},
                                        {"value": "recette", "label": "Recette"},
                                        {"value": "integration", "label": "Intégration"},
                                        {"value": "developpement", "label": "Développement"},
                                        {"value": "autre", "label": "Autre"},
                                    ],
                                },
                                {
                                    "key": "type_solution",
                                    "label": "Type",
                                    "type": "text",
                                    "placeholder": "ERP, ESB, API Gateway...",
                                },
                                {
                                    "key": "localisation",
                                    "label": "Localisation",
                                    "type": "text",
                                },
                            ]
                        },
                    },
                    {
                        "key": "solutions_commentaires",
                        "label": "Commentaires sur les solutions",
                        "type": "long_text",
                        "config": {"rows": 12},
                    },
                ),
            },
            {
                "slug": "briques-techniques",
                "title": "Briques (Composants Techniques)",
                "entries": (
                    {
                        "key": "briques",
                        "label": "Briques techniques",
                        "type": "repeater",
                        "config": {
                            "columns": [
                                {"key": "brique_id", "label": "ID", "type": "text"},
                                {"key": "nom", "label": "Nom", "type": "text"},
                                {
                                    "key": "description",
                                    "label": "Description",
                                    "type": "textarea",
                                    "rows": 4,
                                    "minHeight": 160,
                                },
                            ]
                        },
                    },
                ),
            },
            {
                "slug": "gestion-identites-acces",
                "title": "Gestion des Identités et des Accès",
                "entries": (
                    {
                        "key": "gouvernance_identites",
                        "label": "Gestion des identités",
                        "type": "repeater",
                        "config": {
                            "columns": [
                                {
                                    "key": "type_identite",
                                    "label": "Type",
                                    "type": "select",
                                    "choices": [
                                        {"value": "metier", "label": "Métier"},
                                        {"value": "administrateur", "label": "Administrateur"},
                                        {"value": "exploitant", "label": "Exploitant"},
                                        {"value": "service", "label": "Service"},
                                    ],
                                },
                                {"key": "identifiant", "label": "ID", "type": "text"},
                                {"key": "identifiant_cible", "label": "ID Cible", "type": "text"},
                                {"key": "idp", "label": "IDP", "type": "text"},
                            ]
                        },
                    },
                    {
                        "key": "gouvernance_identites_commentaires",
                        "label": "Commentaires",
                        "type": "long_text",
                        "config": {"rows": 12},
                    },
                ),
            },
            {
                "slug": "schemas",
                "title": "Schémas",
                "entries": (_build_drawio_repeater_entry("schemas", "Schémas", allow_import=False),),
            },
            {
                "slug": "flux",
                "title": "Flux",
                "entries": (
                    {
                        "key": "flux",
                        "label": "Flux applicatifs",
                        "type": "repeater",
                        "config": {
                            "columns": [
                                {
                                    "key": "statut",
                                    "label": "Statut",
                                    "type": "select",
                                    "choices": [
                                        {"value": "propose", "label": "Proposé"},
                                        {"value": "valide", "label": "Validé"},
                                        {"value": "deprecie", "label": "Déprécié"},
                                    ],
                                },
                                {"key": "flux_id", "label": "ID", "type": "text"},
                                {"key": "source", "label": "Source", "type": "text"},
                                {"key": "cible", "label": "Cible", "type": "text"},
                                {
                                    "key": "protocole",
                                    "label": "Protocole",
                                    "type": "text",
                                    "placeholder": "TCP, UDP, HTTP, etc.",
                                },
                                {"key": "port", "label": "Port", "type": "text"},
                                {
                                    "key": "chiffrement",
                                    "label": "Chiffrement",
                                    "type": "select",
                                    "choices": [
                                        {"value": "oui", "label": "Oui"},
                                        {"value": "non", "label": "Non"},
                                    ],
                                },
                                {
                                    "key": "authentification",
                                    "label": "Authentification",
                                    "type": "select",
                                    "choices": [
                                        {"value": "oui", "label": "Oui"},
                                        {"value": "non", "label": "Non"},
                                    ],
                                },
                            ]
                        },
                    },
                ),
            },
        ),
    },
    {
        "slug": "cybersecurite",
        "title": "CYBERSÉCURITÉ",
        "description": "Évaluations et mesures cyber.",
        "allowed_roles": ["analyste-secu", "rssi"],
        "parts": (
            {
                "slug": "analyse-cyber",
                "title": "Analyse Cyber Globale",
                "entries": (
                    {
                        "key": "analyse_cyber_globale",
                        "label": "Analyse cyber globale",
                        "type": "long_text",
                        "config": {"rows": 6},
                    },
                ),
            },
            {
                "slug": "rgpd",
                "title": "Règlement Général sur la Protection des Données (RGPD)",
                "description": (
                    "La collecte, le traitement et le stockage de DCP doit être consenti, légitime, "
                    "faire l'objet d'une étude précisant les finalités ainsi que les impacts sur la protection "
                    "de la donnée (PIA). Tout manquement à ces obligations exposera à des sanctions légales."
                ),
                "entries": (
                    {
                        "key": "manipule_dcp",
                        "label": "L'application manipule des DCP",
                        "type": "boolean",
                    },
                    {
                        "key": "commentaires_types_dcp",
                        "label": "Commentaires sur les types de DCP traitées",
                        "type": "long_text",
                        "config": {"rows": 4},
                    },
                ),
            },
            {
                "slug": "derogations-pssi",
                "title": "Dérogation(s) à la PSSI",
                "entries": (
                    {
                        "key": "derogations_pssi",
                        "label": "Dérogations PSSI",
                        "type": "repeater",
                        "config": {
                            "columns": [
                                {"key": "derogation_id", "label": "ID", "type": "text"},
                                {
                                    "key": "statut",
                                    "label": "Statut",
                                    "type": "select",
                                    "choices": [
                                        {"value": "en_cours", "label": "En cours"},
                                        {"value": "expire", "label": "Expirée"},
                                        {"value": "en_attente", "label": "En attente"},
                                    ],
                                },
                                {"key": "date_debut", "label": "Début de validité", "type": "date"},
                                {"key": "date_fin", "label": "Fin de validité", "type": "date"},
                                {"key": "descriptif", "label": "Descriptif", "type": "textarea", "rows": 2},
                            ]
                        },
                    },
                ),
            },
            {
                "slug": "risques",
                "title": "Risques",
                "entries": (
                    {
                        "key": "analyse_risques",
                        "label": "Risques identifiés",
                        "type": "repeater",
                        "config": {
                            "columns": [
                                {"key": "risque_id", "label": "ID risque", "type": "text"},
                                {
                                    "key": "criticite",
                                    "label": "Criticité",
                                    "type": "select",
                                    "choices": [
                                        {"value": "mineur", "label": "Mineur"},
                                        {"value": "majeur", "label": "Majeur"},
                                        {"value": "critique", "label": "Critique"},
                                    ],
                                },
                                {"key": "derniere_etude", "label": "Dernière étude", "type": "date"},
                                {"key": "descriptif", "label": "Descriptif", "type": "textarea", "rows": 2},
                            ]
                        },
                    },
                ),
            },
            {
                "slug": "plan-traitement-risques",
                "title": "Plan de Traitement des Risques",
                "entries": (
                    {
                        "key": "plan_traitement_risques",
                        "label": "Actions de traitement",
                        "type": "repeater",
                        "config": {
                            "columns": [
                                {"key": "pdt_id", "label": "ID PDT", "type": "text"},
                                {"key": "risque_id", "label": "ID risque", "type": "text"},
                                {
                                    "key": "statut",
                                    "label": "Statut",
                                    "type": "select",
                                    "choices": [
                                        {"value": "a_faire", "label": "À faire"},
                                        {"value": "terminee", "label": "Terminée"},
                                        {"value": "en_cours", "label": "En cours"},
                                    ],
                                },
                                {"key": "echeance", "label": "Échéance", "type": "date"},
                                {
                                    "key": "action",
                                    "label": "Action",
                                    "type": "select",
                                    "choices": [
                                        {"value": "suppression", "label": "Suppression"},
                                        {"value": "reduction", "label": "Réduction"},
                                        {"value": "acceptation", "label": "Acceptation"},
                                        {"value": "transfert", "label": "Transfert"},
                                    ],
                                },
                                {
                                    "key": "criticite_residuelle",
                                    "label": "Criticité résiduelle",
                                    "type": "select",
                                    "choices": [
                                        {"value": "nulle", "label": "Nulle"},
                                        {"value": "mineure", "label": "Mineure"},
                                        {"value": "majeure", "label": "Majeure"},
                                        {"value": "critique", "label": "Critique"},
                                    ],
                                },
                                {"key": "descriptif", "label": "Descriptif", "type": "textarea", "rows": 2},
                            ]
                        },
                    },
                ),
            },
        ),
    },
    {
        "slug": "exploitation",
        "title": "EXPLOITATION",
        "description": "Préparation à l'exploitation et à l'exploitation continue.",
        "allowed_roles": ["infra-exploitation"],
        "parts": (
            {
                "slug": "ressources-solution",
                "title": "Ressources de la solution",
                "entries": (
                    {
                        "key": "ressources_existantes",
                        "label": "Ressources sans modification",
                        "type": "repeater",
                        "config": {
                            "columns": [
                                {"key": "id", "label": "ID", "type": "text"},
                                {
                                    "key": "environnement",
                                    "label": "Environnement (test, préprod…)",
                                    "type": "select",
                                    "choices": [
                                        {"value": "production", "label": "Production"},
                                        {"value": "preproduction", "label": "Préproduction"},
                                        {"value": "recette", "label": "Recette"},
                                        {"value": "integration", "label": "Intégration"},
                                        {"value": "developpement", "label": "Développement"},
                                        {"value": "autre", "label": "Autre"},
                                    ],
                                },
                                {
                                    "key": "clouder",
                                    "label": "Clouder",
                                    "type": "select",
                                    "choices": [
                                        {"value": "on_prem", "label": "On-prem"},
                                        {"value": "cloud", "label": "Cloud"},
                                    ],
                                },
                                {
                                    "key": "type_service",
                                    "label": "Type de Service",
                                    "type": "select",
                                    "choices": [
                                        {"value": "iaas", "label": "IaaS"},
                                        {"value": "paas", "label": "PaaS"},
                                        {"value": "saas", "label": "SaaS"},
                                        {"value": "caas", "label": "CaaS"},
                                        {"value": "faas", "label": "FaaS"},
                                        {"value": "autre", "label": "Autre"},
                                    ],
                                },
                                {"key": "type_gabarit", "label": "Type de gabarit", "type": "text"},
                                {
                                    "key": "type_serveur",
                                    "label": "Type de serveur",
                                    "type": "select",
                                    "choices": [
                                        {"value": "virtuel", "label": "Virtuel"},
                                        {"value": "physique", "label": "Physique"},
                                    ],
                                },
                                {
                                    "key": "nb_instances",
                                    "label": "Nombre d’instances",
                                    "type": "text",
                                    "placeholder": "Ex: 3",
                                },
                                {
                                    "key": "anti_affinite",
                                    "label": "Anti-Affinité",
                                    "type": "select",
                                    "choices": [
                                        {"value": "oui", "label": "Oui"},
                                        {"value": "non", "label": "Non"},
                                    ],
                                },
                                {
                                    "key": "compute",
                                    "label": "Compute",
                                    "type": "text",
                                    "placeholder": "Ex: 4 vCPU",
                                },
                                {
                                    "key": "compute_garanti",
                                    "label": "Compute Garanti",
                                    "type": "select",
                                    "choices": [
                                        {"value": "oui", "label": "Oui"},
                                        {"value": "non", "label": "Non"},
                                    ],
                                },
                                {
                                    "key": "quantite_memoire_go",
                                    "label": "Quantité Mémoire (Go)",
                                    "type": "text",
                                    "placeholder": "Ex: 16",
                                },
                                {
                                    "key": "quantite_stockage_go",
                                    "label": "Quantité Stockage (Go)",
                                    "type": "text",
                                    "placeholder": "Ex: 200",
                                },
                                {
                                    "key": "haute_disponibilite",
                                    "label": "Haute disponibilité",
                                    "type": "select",
                                    "choices": [
                                        {"value": "oui", "label": "Oui"},
                                        {"value": "non", "label": "Non"},
                                    ],
                                },
                            ]
                        },
                    },
                    {
                        "key": "ressources_a_ajouter",
                        "label": "Ressources à ajouter",
                        "type": "repeater",
                        "config": {
                            "columns": [
                                {"key": "id", "label": "ID", "type": "text"},
                                {
                                    "key": "environnement",
                                    "label": "Environnement (test, préprod…)",
                                    "type": "select",
                                    "choices": [
                                        {"value": "production", "label": "Production"},
                                        {"value": "preproduction", "label": "Préproduction"},
                                        {"value": "recette", "label": "Recette"},
                                        {"value": "integration", "label": "Intégration"},
                                        {"value": "developpement", "label": "Développement"},
                                        {"value": "autre", "label": "Autre"},
                                    ],
                                },
                                {
                                    "key": "clouder",
                                    "label": "Clouder",
                                    "type": "select",
                                    "choices": [
                                        {"value": "on_prem", "label": "On-prem"},
                                        {"value": "cloud", "label": "Cloud"},
                                    ],
                                },
                                {
                                    "key": "type_service",
                                    "label": "Type de Service",
                                    "type": "select",
                                    "choices": [
                                        {"value": "iaas", "label": "IaaS"},
                                        {"value": "paas", "label": "PaaS"},
                                        {"value": "saas", "label": "SaaS"},
                                        {"value": "caas", "label": "CaaS"},
                                        {"value": "faas", "label": "FaaS"},
                                        {"value": "autre", "label": "Autre"},
                                    ],
                                },
                                {"key": "type_gabarit", "label": "Type de gabarit", "type": "text"},
                                {
                                    "key": "type_serveur",
                                    "label": "Type de serveur",
                                    "type": "select",
                                    "choices": [
                                        {"value": "virtuel", "label": "Virtuel"},
                                        {"value": "physique", "label": "Physique"},
                                    ],
                                },
                                {
                                    "key": "nb_instances",
                                    "label": "Nombre d’instances",
                                    "type": "text",
                                    "placeholder": "Ex: 3",
                                },
                                {
                                    "key": "anti_affinite",
                                    "label": "Anti-Affinité",
                                    "type": "select",
                                    "choices": [
                                        {"value": "oui", "label": "Oui"},
                                        {"value": "non", "label": "Non"},
                                    ],
                                },
                                {
                                    "key": "compute",
                                    "label": "Compute",
                                    "type": "text",
                                    "placeholder": "Ex: 4 vCPU",
                                },
                                {
                                    "key": "compute_garanti",
                                    "label": "Compute Garanti",
                                    "type": "select",
                                    "choices": [
                                        {"value": "oui", "label": "Oui"},
                                        {"value": "non", "label": "Non"},
                                    ],
                                },
                                {
                                    "key": "quantite_memoire_go",
                                    "label": "Quantité Mémoire (Go)",
                                    "type": "text",
                                    "placeholder": "Ex: 16",
                                },
                                {
                                    "key": "quantite_stockage_go",
                                    "label": "Quantité Stockage (Go)",
                                    "type": "text",
                                    "placeholder": "Ex: 200",
                                },
                                {
                                    "key": "haute_disponibilite",
                                    "label": "Haute disponibilité",
                                    "type": "select",
                                    "choices": [
                                        {"value": "oui", "label": "Oui"},
                                        {"value": "non", "label": "Non"},
                                    ],
                                },
                            ]
                        },
                    },
                    {
                        "key": "ressources_a_supprimer",
                        "label": "Ressources à supprimer",
                        "type": "repeater",
                        "config": {
                            "columns": [
                                {"key": "id", "label": "ID", "type": "text"},
                                {
                                    "key": "environnement",
                                    "label": "Environnement (test, préprod…)",
                                    "type": "select",
                                    "choices": [
                                        {"value": "production", "label": "Production"},
                                        {"value": "preproduction", "label": "Préproduction"},
                                        {"value": "recette", "label": "Recette"},
                                        {"value": "integration", "label": "Intégration"},
                                        {"value": "developpement", "label": "Développement"},
                                        {"value": "autre", "label": "Autre"},
                                    ],
                                },
                                {
                                    "key": "clouder",
                                    "label": "Clouder",
                                    "type": "select",
                                    "choices": [
                                        {"value": "on_prem", "label": "On-prem"},
                                        {"value": "cloud", "label": "Cloud"},
                                    ],
                                },
                                {
                                    "key": "type_service",
                                    "label": "Type de Service",
                                    "type": "select",
                                    "choices": [
                                        {"value": "iaas", "label": "IaaS"},
                                        {"value": "paas", "label": "PaaS"},
                                        {"value": "saas", "label": "SaaS"},
                                        {"value": "caas", "label": "CaaS"},
                                        {"value": "faas", "label": "FaaS"},
                                        {"value": "autre", "label": "Autre"},
                                    ],
                                },
                                {"key": "type_gabarit", "label": "Type de gabarit", "type": "text"},
                                {
                                    "key": "type_serveur",
                                    "label": "Type de serveur",
                                    "type": "select",
                                    "choices": [
                                        {"value": "virtuel", "label": "Virtuel"},
                                        {"value": "physique", "label": "Physique"},
                                    ],
                                },
                                {
                                    "key": "nb_instances",
                                    "label": "Nombre d’instances",
                                    "type": "text",
                                    "placeholder": "Ex: 3",
                                },
                                {
                                    "key": "anti_affinite",
                                    "label": "Anti-Affinité",
                                    "type": "select",
                                    "choices": [
                                        {"value": "oui", "label": "Oui"},
                                        {"value": "non", "label": "Non"},
                                    ],
                                },
                                {
                                    "key": "compute",
                                    "label": "Compute",
                                    "type": "text",
                                    "placeholder": "Ex: 4 vCPU",
                                },
                                {
                                    "key": "compute_garanti",
                                    "label": "Compute Garanti",
                                    "type": "select",
                                    "choices": [
                                        {"value": "oui", "label": "Oui"},
                                        {"value": "non", "label": "Non"},
                                    ],
                                },
                                {
                                    "key": "quantite_memoire_go",
                                    "label": "Quantité Mémoire (Go)",
                                    "type": "text",
                                    "placeholder": "Ex: 16",
                                },
                                {
                                    "key": "quantite_stockage_go",
                                    "label": "Quantité Stockage (Go)",
                                    "type": "text",
                                    "placeholder": "Ex: 200",
                                },
                                {
                                    "key": "haute_disponibilite",
                                    "label": "Haute disponibilité",
                                    "type": "select",
                                    "choices": [
                                        {"value": "oui", "label": "Oui"},
                                        {"value": "non", "label": "Non"},
                                    ],
                                },
                            ]
                        },
                    },
                ),
            },
            {
                "slug": "supervision-monitoring",
                "title": "Supervision & Monitoring",
                "entries": (
                    {
                        "key": "kpi_a_superviser",
                        "label": "KPI à superviser",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                    {
                        "key": "logs_attendus",
                        "label": "Logs attendus (format, volumétrie…)",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                    {
                        "key": "alerting_attendu",
                        "label": "Alerting attendu",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                    {
                        "key": "outillage_monitoring",
                        "label": "Outillage",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                ),
            },
            {
                "slug": "sauvegardes-restauration",
                "title": "Sauvegardes & Restauration",
                "entries": (
                    {
                        "key": "donnees_a_sauvegarder",
                        "label": "Données à sauvegarder",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                    {
                        "key": "frequence_sauvegarde",
                        "label": "Fréquence",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                    {
                        "key": "procedure_restoration",
                        "label": "Procédure de restauration",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                    {
                        "key": "tests_restoration_envisages",
                        "label": "Tests de restauration envisagés",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                ),
            },
            {
                "slug": "securite-conformite-exploitation",
                "title": "Sécurité / Conformité",
                "entries": (
                    {
                        "key": "gestion_des_acces",
                        "label": "Gestion des accès",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                    {
                        "key": "traces_audit",
                        "label": "Traces d’audit",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                    {
                        "key": "chiffrement",
                        "label": "Chiffrement (repos, transit)",
                        "type": "long_text",
                        "config": {"rows": 5},
                    },
                ),
            },
            {
                "slug": "support-exploitation",
                "title": "Support & Exploitation",
                "entries": (
                    {
                        "key": "niveau_support",
                        "label": "Niveau de support (N1 / N2 / N3)",
                        "type": "long_text",
                        "config": {"rows": 4},
                    },
                    {
                        "key": "raci_exploitation",
                        "label": "RACI exploitation",
                        "type": "long_text",
                        "config": {"rows": 4},
                    },
                    {
                        "key": "criticite",
                        "label": "Criticité",
                        "type": "text",
                        "config": {
                            "widget": "radio",
                            "choices": [
                                {"value": "standard", "label": "Standard"},
                                {"value": "sensible", "label": "Sensible"},
                                {"value": "critique", "label": "Critique"},
                            ],
                        },
                    },
                    {
                        "key": "sous_astreinte",
                        "label": "Sous-astreinte",
                        "type": "text",
                        "config": {
                            "widget": "radio",
                            "choices": [
                                {"value": "oui", "label": "Oui"},
                                {"value": "non", "label": "Non"},
                            ],
                        },
                    },
                    {
                        "key": "obligation_pra",
                        "label": "Obligation de PRA",
                        "type": "text",
                        "config": {
                            "widget": "radio",
                            "choices": [
                                {"value": "oui", "label": "Oui"},
                                {"value": "non", "label": "Non"},
                            ],
                        },
                    },
                    {
                        "key": "dima",
                        "label": "DIMA",
                        "type": "text",
                        "config": {
                            "help_text": "Durée en jours/heures (ex: 2j / 6h).",
                            "placeholder": "Ex: 2j / 6h",
                            "pattern": r"^\s*\d+\s*(j|jour|jours|h|heure|heures)(\s*/\s*\d+\s*(j|jour|jours|h|heure|heures))?\s*$",
                            "pattern_message": "Saisir une durée en jours/heures (ex: 2j / 6h).",
                        },
                    },
                    {
                        "key": "pdma",
                        "label": "PDMA",
                        "type": "text",
                        "config": {
                            "help_text": "Durée en jours/heures (ex: 3j / 12h).",
                            "placeholder": "Ex: 3j / 12h",
                            "pattern": r"^\s*\d+\s*(j|jour|jours|h|heure|heures)(\s*/\s*\d+\s*(j|jour|jours|h|heure|heures))?\s*$",
                            "pattern_message": "Saisir une durée en jours/heures (ex: 3j / 12h).",
                        },
                    },
                ),
            },
        ),
    },
    {
        "slug": "validation",
        "title": "VALIDATION",
        "description": "Synthèse des validations et arbitrages.",
        "allowed_roles": [],
        "parts": (
            {
                "slug": "suivi-validation",
                "title": "Suivi des sections",
                "description": "Liste des sections et de leur statut (validé, en cours, bloqué...).",
                "entries": (
                    {
                        "key": "suivi_sections",
                        "label": "Statuts des sections",
                        "type": "repeater",
                        "config": {
                            "columns": [
                                {
                                    "key": "section",
                                    "label": "Section",
                                    "type": "text",
                                    "placeholder": "Ex: Urbanisme, Architecture...",
                                },
                                {
                                    "key": "statut",
                                    "label": "Statut",
                                    "type": "select",
                                    "choices": [
                                        {"value": "valide", "label": "Validé"},
                                        {"value": "en_cours", "label": "En cours"},
                                        {"value": "bloque", "label": "Bloqué"},
                                        {"value": "non_demarre", "label": "Non démarré"},
                                    ],
                                },
                                {
                                    "key": "commentaire",
                                    "label": "Commentaire",
                                    "type": "textarea",
                                    "rows": 2,
                                    "minHeight": 120,
                                },
                            ]
                        },
                    },
                ),
            },
        ),
    },
)


DEFAULT_DAT_SECTION_DEFINITIONS: Tuple[Dict[str, Any], ...] = tuple(
    {
        "slug": blueprint["slug"],
        "title": blueprint["title"],
        "description": blueprint.get("description", ""),
        "allowed_roles": blueprint.get("allowed_roles", []),
        "parts": _normalise_parts(blueprint["slug"], blueprint.get("parts")),
    }
    for blueprint in SECTION_BLUEPRINTS
)

SECTION_BLUEPRINT_MAP: Dict[str, Dict[str, Any]] = {
    blueprint["slug"]: blueprint for blueprint in SECTION_BLUEPRINTS
}


def _find_blueprint_part(section_slug: str, part_slug: str) -> Optional[Dict[str, Any]]:
    blueprint = SECTION_BLUEPRINT_MAP.get(section_slug)
    if not blueprint:
        return None
    for part in blueprint.get("parts", ()):
        if part["slug"] == part_slug:
            return part
    return None


def _resolve_models(apps=None):
    if apps is not None:
        DATSectionModel = apps.get_model("dat", "DATSection")
        try:
            DATSubSectionModel = apps.get_model("dat", "DATSubSection")
        except LookupError:
            DATSubSectionModel = apps.get_model("dat", "DATSectionPart")
        try:
            DATPartModel = apps.get_model("dat", "DATPart")
        except LookupError:
            DATPartModel = apps.get_model("dat", "DATPartEntry")
        RoleModel = apps.get_model("users", "Role")
    else:
        from users.models import Role as RoleModel  # type: ignore

        from .models import DATPart as DATPartModel  # noqa: WPS433
        from .models import DATSection as DATSectionModel  # noqa: WPS433
        from .models import DATSubSection as DATSubSectionModel  # noqa: WPS433

    return DATSectionModel, DATSubSectionModel, DATPartModel, RoleModel


def _section_sub_section_manager(section):
    return getattr(section, "sub_sections", getattr(section, "parts", None))


def _sub_section_entries_manager(sub_section):
    return getattr(sub_section, "parts", getattr(sub_section, "entries", None))


def _dat_part_fk_field(dat_part_model):
    field_names = {field.name for field in dat_part_model._meta.get_fields()}
    return "sub_section" if "sub_section" in field_names else "part"


def _initialise_validation_statuses(entry, section) -> None:
    """
    Populate the validation status table with default "en cours" rows for each section.
    """
    if not entry or entry.key != "suivi_sections":
        return
    dat = getattr(section, "dat", None)
    if dat is None:
        return
    try:
        sections = (
            dat.sections.exclude(slug="validation")
            .order_by("order", "id")
            .values("title")
        )
    except Exception:
        sections = ()
    rows = [{"section": item["title"], "statut": "en_cours", "commentaire": ""} for item in sections]
    entry.update_value(rows)


def ensure_default_sections(dat, *, apps=None) -> None:
    """
    Ensure the default DAT sections structure exists for the given DAT instance.
    """
    DATSectionModel, DATSubSectionModel, DATPartModel, RoleModel = _resolve_models(apps)
    part_fk_field = _dat_part_fk_field(DATPartModel)
    db_alias = getattr(dat._state, "db", None) or "default"

    with transaction.atomic(using=db_alias):
        for section_order, section_definition in enumerate(DEFAULT_DAT_SECTION_DEFINITIONS):
            section_defaults = {
                "title": section_definition["title"],
                "description": section_definition.get("description", ""),
                "order": section_order,
            }
            section, _ = DATSectionModel.objects.using(db_alias).get_or_create(
                dat_id=dat.pk,
                slug=section_definition["slug"],
                defaults=section_defaults,
            )

            section_updates = []
            for field, value in section_defaults.items():
                if getattr(section, field) != value:
                    setattr(section, field, value)
                    section_updates.append(field)
            if section_updates:
                section.save(update_fields=section_updates)

            allowed_slugs: Iterable[str] = section_definition.get("allowed_roles", [])
            if allowed_slugs is not None:
                roles = list(RoleModel.objects.using(db_alias).filter(slug__in=allowed_slugs))
                section.allowed_roles.set(roles)

            sub_section_manager = _section_sub_section_manager(section)
            existing_sub_sections = {item.slug: item for item in sub_section_manager.all()} if sub_section_manager else {}
            blueprint_parts = section_definition.get("parts", ())
            expected_part_slugs = {part["slug"] for part in blueprint_parts}

            for part_order, part_definition in enumerate(blueprint_parts):
                part_defaults = {
                    "title": part_definition["title"],
                    "description": part_definition.get("description", ""),
                    "order": part_order,
                }
                sub_section = existing_sub_sections.get(part_definition["slug"])
                if sub_section is None:
                    sub_section = DATSubSectionModel.objects.using(db_alias).create(
                        section=section,
                        slug=part_definition["slug"],
                        **part_defaults,
                    )
                else:
                    part_updates = []
                    for field, value in part_defaults.items():
                        if getattr(sub_section, field) != value:
                            setattr(sub_section, field, value)
                            part_updates.append(field)
                    if part_updates:
                        sub_section.save(update_fields=part_updates)

                entry_manager = _sub_section_entries_manager(sub_section)
                existing_entries = {entry.key: entry for entry in entry_manager.all()} if entry_manager else {}
                expected_entry_keys = {entry["key"] for entry in part_definition.get("entries", ())}

                allowed_sub_roles = part_definition.get("allowed_roles")
                if allowed_sub_roles is not None and hasattr(sub_section, "allowed_roles"):
                    roles = list(RoleModel.objects.using(db_alias).filter(slug__in=allowed_sub_roles))
                    sub_section.allowed_roles.set(roles)

                for entry_order, entry_definition in enumerate(part_definition.get("entries", ())):
                    entry_defaults = {
                        "label": entry_definition["label"],
                        "data_type": entry_definition["type"],
                        "order": entry_order,
                        "required": entry_definition.get("required", False),
                        "config": entry_definition.get("config"),
                    }
                    entry = existing_entries.get(entry_definition["key"])
                    if entry is None:
                        creation_kwargs = {
                            part_fk_field: sub_section,
                            "key": entry_definition["key"],
                            **entry_defaults,
                        }
                        entry = DATPartModel.objects.using(db_alias).create(**creation_kwargs)
                        _initialise_validation_statuses(entry, section)
                    else:
                        entry_updates = []
                        for field, value in entry_defaults.items():
                            if getattr(entry, field) != value:
                                setattr(entry, field, value)
                                entry_updates.append(field)
                        if entry_updates:
                            entry.save(update_fields=entry_updates + ["updated_at"])
                        _initialise_validation_statuses(entry, section)

                # Remove entries no longer defined
                removable_entries = [
                    entry for key, entry in existing_entries.items() if key not in expected_entry_keys
                ]
                for entry in removable_entries:
                    entry.delete()

            # Remove parts no longer defined
            removable_sub_sections = [
                part for slug, part in existing_sub_sections.items() if slug not in expected_part_slugs
            ]
            for sub_section in removable_sub_sections:
                sub_section.delete()


def _serialise_config(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _configs_match(left: Any, right: Any) -> bool:
    if left in (None, {}) and right in (None, {}):
        return True
    return _serialise_config(left) == _serialise_config(right)


def dat_sections_need_sync(dat) -> bool:
    """
    Determine whether the DAT sections deviate from the expected blueprint definitions.
    """
    expected_section_order = [blueprint["slug"] for blueprint in SECTION_BLUEPRINTS]
    actual_section_order = list(
        dat.sections.order_by("order", "id").values_list("slug", flat=True)
    )
    if actual_section_order != expected_section_order[: len(actual_section_order)] or len(actual_section_order) != len(expected_section_order):
        return True

    sections = dat.sections.all()
    for section in sections:
        blueprint = SECTION_BLUEPRINT_MAP.get(section.slug)
        if not blueprint:
            continue
        blueprint_parts = blueprint.get("parts", ())
        if not blueprint_parts:
            continue
        expected_part_slugs = {part["slug"] for part in blueprint_parts}
        sub_section_manager = _section_sub_section_manager(section)
        if not sub_section_manager:
            return True
        actual_part_slugs = set(sub_section_manager.values_list("slug", flat=True))
        if actual_part_slugs != expected_part_slugs:
            return True
        for sub_section in sub_section_manager.all():
            matching_part = next((item for item in blueprint_parts if item["slug"] == sub_section.slug), None)
            if matching_part is None:
                return True
            expected_entry_keys = {entry["key"] for entry in matching_part.get("entries", ())}
            entry_manager = _sub_section_entries_manager(sub_section)
            if not entry_manager:
                return True
            actual_entry_keys = set(entry_manager.values_list("key", flat=True))
            if actual_entry_keys != expected_entry_keys:
                return True
            blueprint_entry_map = {entry["key"]: entry for entry in matching_part.get("entries", ())}
            for part in entry_manager.all():
                blueprint_entry = blueprint_entry_map.get(part.key)
                if blueprint_entry is None:
                    return True
                if part.data_type != blueprint_entry.get("type"):
                    return True
                if part.label != blueprint_entry.get("label"):
                    return True
                if not _configs_match(part.config or None, blueprint_entry.get("config")):
                    return True
    return False


def sync_dat_sections_if_needed(dat) -> bool:
    """
    Ensure the DAT sections match the current blueprint definitions.
    Returns True if changes were applied.
    """
    if not getattr(dat, "pk", None):
        return False
    if not dat_sections_need_sync(dat):
        return False
    ensure_default_sections(dat)
    cache = getattr(dat, "_prefetched_objects_cache", None)
    if cache:
        cache.pop("sections", None)
    return True
