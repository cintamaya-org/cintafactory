from __future__ import annotations

import random

from django import template
from django.urls import NoReverseMatch, reverse

from diagrams.models import Diagram

register = template.Library()

DEFAULT_ICON_VARIANT = "material-icons"
MATERIAL_SYMBOLS_VARIANT = "material-symbols-outlined"

SECTION_PART_ICON_MAP = {
    "informations-generales": {
        "informations-administratives": {"name": "badge", "variant": MATERIAL_SYMBOLS_VARIANT},
        "description-solution": {"name": "description", "variant": MATERIAL_SYMBOLS_VARIANT},
    },
    "besoins": {
        "typologie-besoin": {"name": "category", "variant": MATERIAL_SYMBOLS_VARIANT},
        "detail-besoin": {"name": "list_alt", "variant": MATERIAL_SYMBOLS_VARIANT},
    },
    "urbanisme": {
        "mapping-urbanisation-si": {"name": "map", "variant": MATERIAL_SYMBOLS_VARIANT},
        "conformite-urbanisme": {"name": "rule", "variant": MATERIAL_SYMBOLS_VARIANT},
        "impact-si-existant": {"name": "device_hub", "variant": MATERIAL_SYMBOLS_VARIANT},
    },
    "exploitation": {
        "ressources-solution": {"name": "dns", "variant": MATERIAL_SYMBOLS_VARIANT},
        "supervision-monitoring": {"name": "monitor", "variant": MATERIAL_SYMBOLS_VARIANT},
        "sauvegardes-restauration": {"name": "cloud_sync", "variant": MATERIAL_SYMBOLS_VARIANT},
        "securite-conformite-exploitation": {"name": "shield_lock", "variant": MATERIAL_SYMBOLS_VARIANT},
        "support-exploitation": {"name": "support_agent", "variant": MATERIAL_SYMBOLS_VARIANT},
    },
    "validation": {
        "suivi-validation": {"name": "task_alt", "variant": MATERIAL_SYMBOLS_VARIANT},
    },
    "architecture": {
        "presentation-generale": "content_paste",
        "hebergement-environnements": "location_on",
        "solutions-utilisees": {"name": "deployed_code", "variant": MATERIAL_SYMBOLS_VARIANT},
        "briques-techniques": {"name": "stack", "variant": MATERIAL_SYMBOLS_VARIANT},
        "gestion-identites-acces": "person",
        "schemas": {"name": "stacks", "variant": MATERIAL_SYMBOLS_VARIANT},
        "flux": "share",
    },
    "cybersecurite": {
        "analyse-cyber": "content_paste",
        "rgpd": {"name": "contract", "variant": MATERIAL_SYMBOLS_VARIANT},
        "derogations-pssi": {"name": "remove_moderator", "variant": MATERIAL_SYMBOLS_VARIANT},
        "risques": {"name": "support", "variant": MATERIAL_SYMBOLS_VARIANT},
        "plan-traitement-risques": {"name": "shield", "variant": MATERIAL_SYMBOLS_VARIANT},
    },
}

DEFAULT_STATUS_ICON_COLOR = "#546e7a"

# TODO later: switch to conditional icons when section status tracking becomes available.
SECTION_STATUS_ICON_CHOICES = (
    {"name": "check_circle", "color": "#2c8f31"},
    {"name": "border_color", "color": "#1565c0"},
    {"name": "timer", "color": "#0097ef"},
    {"name": "plagiarism", "color": "#6a1b9a"},
    {"name": "error", "color": "#000000"},
    {"name": "cancel", "color": "#FF0000"},
)


@register.filter
def get_item(mapping, key):
    if isinstance(mapping, dict):
        return mapping.get(key)
    return None


@register.filter
def dat_columns(config):
    if isinstance(config, dict):
        columns = config.get("columns")
        if isinstance(columns, list):
            return columns
    return []


def _normalise_icon_config(icon_config):
    if not icon_config:
        return None
    if isinstance(icon_config, str):
        return {"name": icon_config, "variant": DEFAULT_ICON_VARIANT}
    if isinstance(icon_config, dict):
        name = icon_config.get("name")
        if not name:
            return None
        variant = icon_config.get("variant") or DEFAULT_ICON_VARIANT
        return {"name": name, "variant": variant}
    return None


@register.filter
def section_part_icon(section_slug, part_slug):
    if not section_slug or not part_slug:
        return None
    icon = SECTION_PART_ICON_MAP.get(str(section_slug), {}).get(str(part_slug))
    return _normalise_icon_config(icon)


@register.simple_tag
def random_section_status_icon():
    choice = random.choice(SECTION_STATUS_ICON_CHOICES)
    if isinstance(choice, dict):
        return {
            "name": choice.get("name"),
            "color": choice.get("color") or DEFAULT_STATUS_ICON_COLOR,
        }
    return {"name": choice, "color": DEFAULT_STATUS_ICON_COLOR}


@register.simple_tag
def diagram_links(diagram_id):
    if diagram_id in (None, ""):
        return None
    try:
        pk = int(str(diagram_id).strip())
    except (TypeError, ValueError):
        return None
    if pk < 1:
        return None
    diagram = Diagram.objects.filter(pk=pk).only("pk", "title").first()
    if diagram is None:
        return None
    try:
        return {
            "pk": diagram.pk,
            "title": diagram.title,
            "detail_url": reverse("diagrams:detail", args=[diagram.pk]),
            "edit_url": reverse("diagrams:edit", args=[diagram.pk]),
            "import_url": reverse("diagrams:import_xml", args=[diagram.pk]),
            "export_url": reverse("diagrams:export_xml", args=[diagram.pk]),
        }
    except NoReverseMatch:
        return None
