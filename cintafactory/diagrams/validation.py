from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

CONTROL_CHARACTERS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
DISALLOWED_DIAGRAM_CHARS_RE = re.compile(r"[<>[\]{}]")
DRAWIO_FORBIDDEN_XML_PATTERN = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
DRAWIO_FORBIDDEN_TAG_PATTERN = re.compile(r"<\s*(script|iframe|object|embed)\b", re.IGNORECASE)
ROOT_TAG_PATTERN = re.compile(r"<\s*([a-zA-Z0-9:_-]+)")
DRAWIO_ALLOWED_ROOT_TAGS = {"mxGraphModel", "mxfile"}


def sanitize_diagram_title(value: str | None) -> str:
    """
    Normalize and validate a diagram title before persisting it.
    Raises a ValidationError when forbidden characters are detected.
    """
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValidationError(_("Le nom du diagramme doit être une chaîne de caractères."))

    normalized = re.sub(r"\s+", " ", value.strip(), flags=re.UNICODE)
    if not normalized:
        raise ValidationError(_("Merci de renseigner un nom de diagramme."))

    if CONTROL_CHARACTERS_RE.search(normalized):
        raise ValidationError(_("Le nom du diagramme contient des caractères de contrôle interdits."))

    if DISALLOWED_DIAGRAM_CHARS_RE.search(normalized):
        raise ValidationError(_("Le nom du diagramme ne peut pas contenir les caractères <, >, {, }, [ ou ]."))

    return normalized


def validate_drawio_xml(xml_payload: str | None) -> str:
    """
    Basic sanity-check for Draw.io payloads to avoid importing arbitrary files.
    Ensures we only persist mxGraph-based documents and blocks dangerous constructs.
    """
    if xml_payload is None:
        raise ValidationError(_("Le fichier diagramme est vide ou invalide."))
    if not isinstance(xml_payload, str):
        raise ValidationError(_("Le diagramme importé doit être du texte UTF-8."))  # pragma: no cover
    content = xml_payload.strip()
    if not content:
        raise ValidationError(_("Le fichier diagramme est vide ou invalide."))

    if DRAWIO_FORBIDDEN_XML_PATTERN.search(content):
        raise ValidationError(_("Les définitions DOCTYPE ou ENTITY sont interdites dans les diagrammes importés."))
    if DRAWIO_FORBIDDEN_TAG_PATTERN.search(content):
        raise ValidationError(_("Le fichier contient des balises non autorisées."))

    match = ROOT_TAG_PATTERN.search(content)
    if not match:
        raise ValidationError(_("Impossible de déterminer le type du diagramme importé."))
    root_tag = match.group(1)
    if root_tag not in DRAWIO_ALLOWED_ROOT_TAGS:
        raise ValidationError(_("Seuls les fichiers Draw.io (.drawio/.xml) sont acceptés."))

    return content
