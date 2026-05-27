from __future__ import annotations

from typing import Tuple

# Ordered list of required DAT participant roles (slug, fallback label)
DAT_REQUIRED_PARTICIPANT_ROLES: Tuple[Tuple[str, str], ...] = (
    ("porteur-demande", "Porteur de la demande"),
    ("architecte-referent", "Architecte referent"),
    ("architecte-technique", "Architecte technique"),
    ("urbaniste", "Urbaniste"),
    ("analyste-secu", "Analyste securite"),
    ("rssi", "RSSI"),
    ("comite-validation", "Comite de validation"),
    ("infra-exploitation", "Infra / Exploitation"),
)

DAT_PORTEUR_ROLE_SLUG = DAT_REQUIRED_PARTICIPANT_ROLES[0][0]
DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS: Tuple[str, ...] = tuple(
    slug for slug, _ in DAT_REQUIRED_PARTICIPANT_ROLES
)
DAT_REQUIRED_PARTICIPANT_ROLE_LABELS = {
    slug: label for slug, label in DAT_REQUIRED_PARTICIPANT_ROLES
}

DAT_STATUS_REQUIRED_ROLES = {
    "nouvelle_demande": ("porteur-demande",),
    "en_cours": ("porteur-demande",),
    "en_attente_de_revue": ("architecte-referent", "comite-validation"),
    "valider": ("architecte-referent",),
    "refuse": ("architecte-referent",),
    "reserve": ("architecte-referent", "porteur-demande"),
}
