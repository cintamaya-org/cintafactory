from __future__ import annotations

import random

from django import template
from django.urls import NoReverseMatch, reverse

from diagrams.models import Diagram

register = template.Library()

DEFAULT_ICON_VARIANT = "material-icons"
MATERIAL_SYMBOLS_VARIANT = "material-symbols-outlined"

SECTION_PART_ICON_MAP = {
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

# TODO later: switch to conditional icons when section status tracking becomes available.
# Proposed mapping:
#   validated -> check_circle
#   in_progress -> border_color
#   pending_prereq -> timer
#   awaiting_review -> plagiarism
#   blocked -> error
#   refused -> cancel
SECTION_STATUS_ICON_CHOICES = (
    "check_circle",
    "border_color",
    "timer",
    "plagiarism",
    "error",
    "cancel",
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
    return random.choice(SECTION_STATUS_ICON_CHOICES)


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
