import json
import logging
import re
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.conf import settings
from django.apps import apps as django_apps
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, F, Prefetch, Q
from django.db.models.functions import TruncMonth
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.text import slugify
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView, FormView
from django.views.decorators.http import require_POST

from material import Fieldset, Layout, Row
from material.frontend.registry import modules as module_registry
from material.frontend.views import CreateModelView, DetailModelView, ListModelView, ModelViewSet, UpdateModelView

from diagrams.models import DrawIODiagram
from diagrams.validation import sanitize_diagram_title
from cintafactory.url_safety import is_http_url

from .attachments import (
    build_attachment_ui_context,
    build_download_filename,
    create_section_attachment,
    delete_section_attachment as delete_section_attachment_file,
    get_attachment_storage,
)
from .constants import (
    DAT_PORTEUR_ROLE_SLUG,
    DAT_REQUIRED_PARTICIPANT_ROLE_LABELS,
    DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS,
    DAT_STATUS_REQUIRED_ROLES,
)
from .drawio_parser import BRIQUE_COLUMNS, FLUX_COLUMNS, dedupe_architecture_rows, parse_architecture_diagram
from .exporters import get_dat_export_model_builder
from .forms import DATForm, DATImportForm, DATSubSectionForm
from .importers import DATImportError, DATImportService
from .models import (
    Application,
    DAT,
    DATPart,
    DATPartEntryType,
    DATPartEntry,
    DATReserveHistory,
    DATReserveHistoryAction,
    DATSection,
    DATSectionAttachment,
    DATSubSection,
    DATStatus,
    DATHistory,
    DATHistoryAction,
)
from .pdf import generate_dat_pdf
from .permissions import (
    filter_dat_queryset_for_user,
    user_can_update_section_status,
    user_is_dat_admin,
    user_is_responsible_for_section,
)
from .sections import (
    SECTION_STATUS_BLOCKED_VALUE,
    SECTION_STATUS_DEFAULT,
    SECTION_STATUS_ENTRY_KEY,
    SECTION_STATUS_VALIDATED_VALUE,
    section_has_attachments,
    section_has_status,
    sync_dat_sections_if_needed,
)
from .tasks import schedule_dat_pdf_generation
from .utils import (
    dat_pdf_export_exists,
    dat_pdf_export_modified_at,
    format_user_display,
    isoformat_datetime,
    localize_datetime,
    open_dat_pdf_export,
    store_dat_pdf_export,
)
from workflows.notifications import create_user_notification


logger = logging.getLogger(__name__)

PORTEUR_ROLE_SLUG = DAT_PORTEUR_ROLE_SLUG
OWNER_EDITABLE_STATUSES = {
    DATStatus.NOUVELLE_DEMANDE,
    DATStatus.EN_COURS,
    DATStatus.RESERVE,
}
FINAL_DAT_STATUSES = {DATStatus.VALIDER, DATStatus.REFUSE}
VALIDATION_STATUS_LABELS = {
    DATStatus.EN_ATTENTE_DE_REVUE.label,
    DATStatus.RESERVE.label,
    DATStatus.VALIDER.label,
    DATStatus.REFUSE.label,
}
HISTORY_ENTRIES_PREFETCH = Prefetch(
    "history_entries",
    queryset=DATHistory.objects.select_related("performed_by").order_by("-performed_at", "-id"),
)
RESERVE_HISTORY_ENTRIES_PREFETCH = Prefetch(
    "reserve_history_entries",
    queryset=DATReserveHistory.objects.select_related("reserved_by").order_by("-reserved_at", "-id"),
)


class ModuleContextMixin:
    """Provide a consistent `current_module` entry for templates that extend module bases."""

    module_app_label = "dat"
    default_base_template = "material/frontend/base_module.html"

    def _resolve_module(self):
        module = None
        request = getattr(self, "request", None)
        if request is not None:
            resolver_match = getattr(request, "resolver_match", None)
            if resolver_match:
                module_label = resolver_match.namespace or resolver_match.app_name
                if module_label:
                    try:
                        module = module_registry.get_module(module_label)
                    except KeyError:
                        module = None
        if module is None and self.module_app_label:
            try:
                module = django_apps.get_app_config(self.module_app_label)
            except LookupError:
                module = None
        return module

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        module = context.get("current_module") or self._resolve_module()
        if module:
            context["current_module"] = module
        elif self.default_base_template:
            context["current_module"] = SimpleNamespace(base_template=self.default_base_template)
        return context


class ModuleAwareListView(ModuleContextMixin, ListModelView):
    pass


class ApplicationListView(ModuleAwareListView):
    template_name = "dat/application_list.html"

    def get_queryset(self):
        return Application.objects.select_related("business_direction").order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        object_list = context.get("object_list")
        if object_list is None:
            # Material's ListModelView may not expose object_list; populate it to keep the template simple.
            object_list = list(self.get_queryset())
            context["object_list"] = object_list
        context["total_applications"] = len(object_list)
        return context


class MyApplicationListView(ModuleContextMixin, LoginRequiredMixin, ListView):
    model = Application
    template_name = "dat/my_application_list.html"
    context_object_name = "object_list"

    def get_queryset(self):
        user = self.request.user
        if user is None or not getattr(user, "is_authenticated", False):
            return Application.objects.none()
        dat_queryset = (
            DAT.objects.filter(
                Q(owner=user)
                | Q(participants__user=user)
                | Q(participants__user__business_group__responsible=user)
            )
            .distinct()
        )
        return (
            Application.objects.filter(pk__in=dat_queryset.values("application_id"))
            .select_related("business_direction")
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        object_list = context.get("object_list")
        if object_list is None:
            object_list = list(self.get_queryset())
            context["object_list"] = object_list
        total_applications = len(object_list) if isinstance(object_list, list) else object_list.count()
        context["total_applications"] = total_applications
        context["can_manage_applications"] = user_can_manage_dat(self.request.user)
        return context


def get_required_roles_for_status(status: str) -> tuple[str, ...]:
    return DAT_STATUS_REQUIRED_ROLES.get(status, ())


REVIEWER_ROLE_SLUGS = {"architecte-referent", "comite-validation"}


def user_can_review_dat(dat: DAT, user) -> bool:
    if dat is None or user is None or not getattr(user, "is_authenticated", False):
        return False
    if user_is_dat_admin(user):
        return True
    user_id = getattr(user, "id", None)
    if user_id is None:
        return False
    for participant in dat.participants.all():
        role = getattr(participant, "role", None)
        if role and role.slug in REVIEWER_ROLE_SLUGS and participant.user_id == user_id:
            return True
    return False


def _are_all_sections_validated(status_map: dict[str, dict] | None) -> bool:
    if not status_map:
        return False
    for status_info in status_map.values():
        if not status_info.get("has_status"):
            continue
        if status_info.get("value") != SECTION_STATUS_VALIDATED_VALUE:
            return False
    return True


def _are_all_sections_responsible_validated(status_map: dict[str, dict] | None) -> bool:
    if not status_map:
        return False
    for status_info in status_map.values():
        if not status_info.get("has_status"):
            continue
        if status_info.get("responsable_value") != SECTION_STATUS_VALIDATED_VALUE:
            return False
    return True


def refresh_dat_status(
    dat: DAT,
    *,
    actor=None,
    force_in_progress: bool = False,
    status_map: dict | None = None,
    status_choices: dict | None = None,
) -> bool:
    """
    Synchronise the DAT status with the completion state of its sections.
    """
    if dat.status in FINAL_DAT_STATUSES:
        return False

    computed_status_map = status_map
    if computed_status_map is None or status_choices is None:
        computed_status_map, status_choices = build_section_status_map(dat)

    all_validated = _are_all_sections_validated(computed_status_map)
    all_responsable_validated = _are_all_sections_responsible_validated(computed_status_map)
    target_status = dat.status

    if all_responsable_validated:
        target_status = DATStatus.VALIDER
    elif dat.status == DATStatus.RESERVE:
        target_status = DATStatus.EN_ATTENTE_DE_REVUE if all_validated else DATStatus.RESERVE
    elif all_validated:
        target_status = DATStatus.EN_ATTENTE_DE_REVUE
    elif dat.status == DATStatus.EN_ATTENTE_DE_REVUE:
        target_status = DATStatus.EN_COURS
    elif force_in_progress:
        target_status = DATStatus.EN_COURS

    if target_status == dat.status:
        return False

    if actor is not None:
        dat._history_actor = actor  # type: ignore[attr-defined]
    dat.status = target_status
    dat.save(update_fields=["status", "updated_at"])
    return True


def build_participant_overview(dat: DAT):
    participant_map = {}
    for participant in dat.participants.all():
        role = getattr(participant, "role", None)
        if role and role.slug in DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS:
            participant_map.setdefault(role.slug, participant)

    required_roles = set(get_required_roles_for_status(dat.status))
    overview = []
    for slug in DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS:
        participant = participant_map.get(slug)
        if participant and participant.role:
            role_label = participant.role.name
        else:
            role_label = DAT_REQUIRED_PARTICIPANT_ROLE_LABELS.get(slug, slug)
        user = participant.user if participant else None
        overview.append(
            {
                "role_slug": slug,
                "role_label": role_label,
                "user": user,
                "user_display": format_user_display(user),
                "participant": participant,
                "is_porteur": slug == DAT_PORTEUR_ROLE_SLUG,
                "is_missing": user is None,
                "is_responsible": slug in required_roles,
            }
        )
    return overview


def get_current_responsibles(dat: DAT):
    required_roles = get_required_roles_for_status(dat.status)
    if not required_roles:
        return []
    participants = {
        getattr(participant.role, "slug", None): participant
        for participant in dat.participants.all()
        if getattr(participant, "role", None) is not None
    }
    responsibles = []
    for slug in required_roles:
        participant = participants.get(slug)
        role_label = DAT_REQUIRED_PARTICIPANT_ROLE_LABELS.get(slug, slug)
        user = getattr(participant, "user", None)
        responsibles.append(
            {
                "role_slug": slug,
                "role_label": role_label,
                "user": user,
                "user_display": format_user_display(user),
                "is_assigned": user is not None,
            }
        )
    return responsibles


def get_dat_history_entries(dat: DAT):
    """
    Return ordered history entries, using any prefetched cache if available to avoid extra queries.
    """
    cache = getattr(dat, "_prefetched_objects_cache", None)
    if cache and "history_entries" in cache:
        return list(cache["history_entries"])
    return list(
        dat.history_entries.select_related("performed_by").order_by("-performed_at", "-id")
    )


def get_dat_reserve_history_entries(dat: DAT):
    """
    Return ordered reserve history entries, using any prefetched cache if available to avoid extra queries.
    """
    cache = getattr(dat, "_prefetched_objects_cache", None)
    if cache and "reserve_history_entries" in cache:
        return list(cache["reserve_history_entries"])
    return list(
        dat.reserve_history_entries.select_related("reserved_by").order_by("-reserved_at", "-id")
    )


def get_dat_validation_history_entries(dat: DAT):
    """
    Return history entries related to validation decisions (DAT status + référent validations).
    """
    entries = []
    for entry in get_dat_history_entries(dat):
        if entry.action == DATHistoryAction.RESPONSIBLE_VALIDATION:
            entries.append(entry)
            continue
        if entry.action == DATHistoryAction.STATUS_CHANGED:
            details = entry.details or {}
            if not isinstance(details, dict):
                continue
            status_from = details.get("from") or ""
            status_to = details.get("to") or ""
            if status_from in VALIDATION_STATUS_LABELS or status_to in VALIDATION_STATUS_LABELS:
                entries.append(entry)
    return entries


def build_dat_reserve_validation_history(dat: DAT):
    combined = []
    for entry in get_dat_reserve_history_entries(dat):
        combined.append(
            {
                "kind": "reserve",
                "timestamp": entry.reserved_at,
                "sequence": entry.id or 0,
                "user_id": entry.reserved_by_id,
                "entry": entry,
            }
        )
    for entry in get_dat_validation_history_entries(dat):
        combined.append(
            {
                "kind": "validation",
                "timestamp": entry.performed_at,
                "sequence": entry.id or 0,
                "user_id": entry.performed_by_id,
                "entry": entry,
            }
        )
    combined.sort(
        key=lambda item: (item["timestamp"] or timezone.now(), item["sequence"]),
        reverse=True,
    )
    return combined


def build_dat_history_user_choices(dat: DAT):
    users_by_id = {}
    owner = getattr(dat, "owner", None)
    owner_id = getattr(owner, "pk", None)
    if owner_id:
        users_by_id[int(owner_id)] = format_user_display(owner)
    try:
        participants = dat.participants.all()
    except Exception:
        participants = []
    for participant in participants:
        user = getattr(participant, "user", None)
        user_id = getattr(user, "pk", None)
        if not user_id:
            continue
        users_by_id.setdefault(int(user_id), format_user_display(user))
    choices = [
        {"id": user_id, "label": label}
        for user_id, label in users_by_id.items()
    ]
    choices.sort(key=lambda item: item["label"].lower())
    return choices


def build_dat_overview_context(dat: DAT, user):
    next_status = get_next_status(dat.status)
    return {
        "dat": dat,
        "participant_overview": build_participant_overview(dat),
        "current_responsibles": get_current_responsibles(dat),
        "owner_editable_statuses": {status.value for status in OWNER_EDITABLE_STATUSES},
        "owner_can_edit": user_is_dat_admin(user),
        "can_create_dat": user_can_create_dat_entities(user),
        "next_status": next_status,
        "next_status_label": DATStatus(next_status).label if next_status else None,
        "can_progress_dat": user_can_progress_dat(dat, user),
        "can_review_dat": user_can_review_dat(dat, user),
    }


def _find_section_status_part(dat: DAT, sections_list: list[DATSection] | None = None) -> DATPart | None:
    if sections_list:
        for section in sections_list:
            if getattr(section, "slug", None) != "validation":
                continue
            try:
                sub_sections = list(section.sub_sections.all())
            except Exception:
                sub_sections = []
            for sub_section in sub_sections:
                try:
                    parts = list(sub_section.parts.all())
                except Exception:
                    parts = []
                for part in parts:
                    if getattr(part, "key", None) == SECTION_STATUS_ENTRY_KEY:
                        return part
    try:
        return (
            DATPart.objects.select_related("sub_section__section")
            .filter(sub_section__section__dat=dat, key=SECTION_STATUS_ENTRY_KEY)
            .first()
        )
    except Exception:
        return None


def _status_choice_map(status_part: DATPart | None) -> dict[str, str]:
    config = status_part.config if isinstance(status_part, DATPart) else None
    if isinstance(config, dict):
        columns = config.get("columns")
        if isinstance(columns, list):
            for column in columns:
                if isinstance(column, dict) and column.get("key") == "statut":
                    choices = column.get("choices")
                    if isinstance(choices, list):
                        mapping: dict[str, str] = {}
                        for choice in choices:
                            if not isinstance(choice, dict):
                                continue
                            value = choice.get("value")
                            if value in (None, ""):
                                continue
                            mapping[str(value)] = choice.get("label", value)
                        if mapping:
                            return mapping
    return {
        SECTION_STATUS_DEFAULT: "En cours",
        SECTION_STATUS_BLOCKED_VALUE: "Bloqué",
        SECTION_STATUS_VALIDATED_VALUE: "Validé",
    }


def _default_status_value(choices: dict[str, str]) -> str:
    if SECTION_STATUS_DEFAULT in choices:
        return SECTION_STATUS_DEFAULT
    if choices:
        return next(iter(choices))
    return SECTION_STATUS_DEFAULT


def reset_section_statuses_to_default(
    dat: DAT,
    *,
    status_map: dict | None = None,
    status_choices: dict | None = None,
) -> None:
    """
    Revert all section statuses to the default value (used when placing a DAT in réserve).
    """
    if status_choices is None or not status_map:
        status_map, status_choices = build_section_status_map(dat)
    status_part = _find_section_status_part(dat)
    if status_part is None or status_choices is None:
        return
    default_status = _default_status_value(status_choices)
    sections = list(dat.sections.order_by("order", "id").select_related("metadata"))
    updated_rows = []
    for section in sections:
        if not section_has_status(section.slug):
            continue
        existing = status_map.get(section.slug, {}) if status_map else {}
        comment = existing.get("commentaire", "") if isinstance(existing, dict) else ""
        updated_rows.append(
            {
                "section": section.title,
                "section_slug": section.slug,
                "statut": default_status,
                "statut_responsable": default_status,
                "reserve_message": "",
                "reserve_by_id": None,
                "reserve_by_display": "",
                "commentaire": comment,
            }
        )
    if updated_rows:
        status_part.update_value(updated_rows)


def build_section_status_map(dat: DAT, sections_list: list[DATSection] | None = None):
    sections = sections_list or list(dat.sections.order_by("order", "id").select_related("metadata"))
    status_part = _find_section_status_part(dat, sections)
    choice_map = _status_choice_map(status_part)
    default_status = _default_status_value(choice_map)
    try:
        raw_rows = status_part.value if status_part else []
    except Exception:
        raw_rows = []
    if not isinstance(raw_rows, list):
        raw_rows = []
    existing_by_slug: dict[str, dict] = {}
    existing_by_title: dict[str, dict] = {}
    stale_rows = False
    for row in raw_rows:
        if not isinstance(row, dict):
            stale_rows = True
            continue
        slug = row.get("section_slug")
        if slug not in (None, ""):
            existing_by_slug[str(slug)] = row
            continue
        label = row.get("section")
        if label not in (None, ""):
            existing_by_title[str(label)] = row
            continue
        stale_rows = True
    status_map: dict[str, dict[str, object]] = {}
    updated_rows: list[dict[str, object]] = []
    dirty = stale_rows
    allowed_identifiers: set[str] = set()
    for section in sections:
        has_status = section_has_status(section.slug)
        if has_status:
            allowed_identifiers.add(section.slug)
            allowed_identifiers.add(section.title)
            current_row = existing_by_slug.get(section.slug) or existing_by_title.get(section.title)
            statut = None
            statut_responsable = None
            reserve_message = ""
            reserve_by_id = None
            reserve_by_display = ""
            comment = ""
            if isinstance(current_row, dict):
                statut = current_row.get("statut")
                statut_responsable = current_row.get("statut_responsable")
                reserve_message = str(current_row.get("reserve_message") or "").strip()
                reserve_by_id = current_row.get("reserve_by_id")
                reserve_by_display = str(current_row.get("reserve_by_display") or "").strip()
                comment = current_row.get("commentaire") or ""
            if not reserve_message:
                reserve_by_id = None
                reserve_by_display = ""
            if not statut:
                statut = default_status
            elif statut not in choice_map:
                statut = default_status
                dirty = True
            if not statut_responsable:
                statut_responsable = default_status
            elif statut_responsable not in choice_map:
                statut_responsable = default_status
                dirty = True
            normalised_row = {
                "section": section.title,
                "section_slug": section.slug,
                "statut": statut,
                "statut_responsable": statut_responsable,
                "reserve_message": reserve_message,
                "reserve_by_id": reserve_by_id,
                "reserve_by_display": reserve_by_display,
                "commentaire": comment,
            }
            updated_rows.append(normalised_row)
            if (
                current_row is None
                or current_row.get("section") != normalised_row["section"]
                or current_row.get("section_slug") != normalised_row["section_slug"]
                or current_row.get("statut") != normalised_row["statut"]
                or current_row.get("statut_responsable") != normalised_row["statut_responsable"]
                or str(current_row.get("reserve_message") or "").strip() != normalised_row["reserve_message"]
                or current_row.get("reserve_by_id") != normalised_row["reserve_by_id"]
                or str(current_row.get("reserve_by_display") or "").strip() != normalised_row["reserve_by_display"]
                or (current_row.get("commentaire") or "") != normalised_row["commentaire"]
            ):
                dirty = True
            status_map[section.slug] = {
                "has_status": True,
                "value": statut,
                "label": choice_map.get(statut, statut),
                "responsable_value": statut_responsable,
                "responsable_label": choice_map.get(statut_responsable, statut_responsable),
                "reserve_message": reserve_message,
                "reserve_by_id": reserve_by_id,
                "reserve_by_display": reserve_by_display,
                "commentaire": comment,
            }
        else:
            status_map[section.slug] = {
                "has_status": False,
                "value": None,
                "label": None,
                "responsable_value": None,
                "responsable_label": None,
                "commentaire": "",
            }
    for label in (*existing_by_slug.keys(), *existing_by_title.keys()):
        if label not in allowed_identifiers:
            dirty = True
            break
    if status_part and dirty:
        status_part.update_value(updated_rows)
    return status_map, choice_map


def section_is_locked(status_info: dict | None, *, dat: DAT | None = None) -> bool:
    if dat is not None:
        if dat.status in FINAL_DAT_STATUSES:
            return True
        return False
    return False


def build_section_payload(
    dat: DAT,
    user,
    section_slug: str | None = None,
    sub_section_slug: str | None = None,
    *,
    section_status_map: dict | None = None,
    section_status_choices: dict | None = None,
):
    def extract_lock_rule(part: DATPart) -> dict[str, object] | None:
        config = part.config if isinstance(part.config, dict) else None
        if not config:
            return None
        rule = config.get("locked_when")
        if not isinstance(rule, dict):
            return None
        controller = rule.get("field")
        raw_values = rule.get("values")
        if not controller or not raw_values:
            return None
        values = raw_values if isinstance(raw_values, (list, tuple)) else [raw_values]
        cleaned = [str(value) for value in values if value not in (None, "")]
        if not cleaned:
            return None
        payload: dict[str, object] = {"field": str(controller), "values": cleaned}
        message = rule.get("message")
        if message not in (None, ""):
            payload["message"] = str(message)
        return payload

    def should_lock_part(part: DATPart, value_map: dict[str, object]) -> bool:
        rule = extract_lock_rule(part)
        if not rule:
            return False
        controller = rule.get("field")
        expected_values = {str(value) for value in rule.get("values", []) if value not in (None, "")}
        if not controller or not expected_values:
            return False
        current_value = value_map.get(str(controller))
        if isinstance(current_value, (list, tuple)):
            return any(str(value) in expected_values for value in current_value if value not in (None, ""))
        if current_value in (None, ""):
            return False
        return str(current_value) in expected_values

    def part_has_drawio_table(entries) -> bool:
        if not entries:
            return False
        for entry in entries:
            if getattr(entry, "data_type", None) != "repeater":
                continue
            config = getattr(entry, "config", None)
            columns = config.get("columns") if isinstance(config, dict) else None
            if not columns:
                continue
            for column in columns:
                if not isinstance(column, dict):
                    continue
                if column.get("drawio") or column.get("render") in {"drawio_diagram", "drawio_actions"}:
                    return True
        return False

    sync_dat_sections_if_needed(dat)
    sections_payload = []
    entry_prefetch = Prefetch(
        "entries",
        queryset=DATPartEntry.objects.order_by("-updated_at", "-id"),
    )
    part_prefetch = Prefetch(
        "parts",
        queryset=DATPart.objects.order_by("order", "id").prefetch_related(entry_prefetch),
    )
    sub_section_prefetch = Prefetch(
        "sub_sections",
        queryset=DATSubSection.objects.order_by("order", "id")
        .prefetch_related("allowed_roles")
        .prefetch_related(part_prefetch),
    )
    attachment_prefetch = Prefetch(
        "attachments",
        queryset=DATSectionAttachment.objects.select_related("uploaded_by").order_by("-created_at", "-id"),
    )
    sections_qs = (
        dat.sections.order_by("order", "id")
        .select_related("metadata")
        .prefetch_related(sub_section_prefetch, attachment_prefetch)
    )
    if section_slug:
        sections_qs = sections_qs.filter(metadata__slug=section_slug)
    sections_list = list(sections_qs)
    if section_slug and not sections_list:
        return []
    if section_status_map is None or section_status_choices is None:
        status_map, status_choices = build_section_status_map(dat)
    else:
        status_map, status_choices = section_status_map, section_status_choices
    default_status_value = _default_status_value(status_choices)
    entry_value_map: dict[str, object] = {}
    for section in sections_list:
        for sub_section in section.sub_sections.all():
            for entry in sub_section.parts.all():
                entry_value_map[entry.key] = entry.value
    try:
        participants = list(dat.participants.select_related("user__business_group__responsible").all())
    except Exception:
        participants = []
    dat._participants_cache = participants  # type: ignore[attr-defined]
    validation_targets: list[DATSection] | None = None
    for section in sections_list:
        section_status = status_map.get(
            section.slug,
            {"has_status": False, "value": None, "label": None, "commentaire": ""},
        )
        is_locked = section_is_locked(section_status, dat=dat)
        section_can_edit = False if section.slug == "validation" else section.can_user_edit(user)
        if dat.status in FINAL_DAT_STATUSES:
            section_can_edit = False
        elif is_locked:
            section_can_edit = False
        attachments_enabled = section_has_attachments(section.slug)
        attachments = list(section.attachments.all()) if attachments_enabled else []
        validation_allowed_sections: dict[str, bool] | None = None
        validation_reserve_allowed_sections: dict[str, bool] | None = None
        validation_reserve_clear_allowed_sections: dict[str, bool] | None = None
        if section.slug == "validation":
            if validation_targets is None:
                try:
                    validation_targets = list(
                        dat.sections.exclude(metadata__slug="validation")
                        .order_by("order", "id")
                        .prefetch_related("allowed_roles")
                    )
                except Exception:
                    validation_targets = []
            validation_allowed_sections = {}
            user_id = getattr(user, "id", None)
            managed_role_ids: set[int] = set()
            if user_is_dat_admin(user):
                managed_role_ids = set()
            else:
                for participant in participants:
                    assignee = getattr(participant, "user", None)
                    group = getattr(assignee, "business_group", None) if assignee is not None else None
                    if group is None:
                        continue
                    if getattr(group, "responsible_id", None) != user_id:
                        continue
                    role_id = getattr(participant, "role_id", None)
                    if role_id is not None:
                        managed_role_ids.add(int(role_id))
            is_any_group_responsible = bool(user_is_dat_admin(user) or managed_role_ids)
            for target in validation_targets:
                if not section_has_status(target.slug):
                    continue
                if dat.status in FINAL_DAT_STATUSES:
                    continue
                if (status_map.get(target.slug) or {}).get("value") != SECTION_STATUS_VALIDATED_VALUE:
                    continue
                if user_is_dat_admin(user):
                    validation_allowed_sections[target.slug] = True
                    continue
                allowed_role_ids = getattr(target, "_allowed_role_ids_cache", None)
                if allowed_role_ids is None:
                    try:
                        allowed_role_ids = set(target.allowed_roles.values_list("pk", flat=True))
                    except Exception:
                        allowed_role_ids = set()
                    target._allowed_role_ids_cache = allowed_role_ids
                if allowed_role_ids and managed_role_ids.intersection({int(pk) for pk in allowed_role_ids}):
                    validation_allowed_sections[target.slug] = True
            if not validation_allowed_sections:
                validation_allowed_sections = None

            if is_any_group_responsible and validation_targets:
                validation_reserve_allowed_sections = {}
                validation_reserve_clear_allowed_sections = {}
                for target in validation_targets:
                    if not section_has_status(target.slug):
                        continue
                    if dat.status in FINAL_DAT_STATUSES:
                        continue
                    if not user_is_dat_admin(user) and user_is_responsible_for_section(dat, target, user, participants=participants):
                        continue
                    info = status_map.get(target.slug) or {}
                    reserve_message = str(info.get("reserve_message") or "").strip()
                    reserve_by_id = info.get("reserve_by_id")
                    if reserve_message and reserve_by_id == user_id:
                        validation_reserve_clear_allowed_sections[target.slug] = True
                    elif not reserve_message:
                        validation_reserve_allowed_sections[target.slug] = True
                if not validation_reserve_allowed_sections:
                    validation_reserve_allowed_sections = None
                if not validation_reserve_clear_allowed_sections:
                    validation_reserve_clear_allowed_sections = None
        parts_payload = []
        for sub_section in section.sub_sections.all():
            if sub_section_slug and sub_section.slug != sub_section_slug:
                continue
            entries = [entry for entry in sub_section.parts.all() if not should_lock_part(entry, entry_value_map)]
            if section.slug == "validation":
                for entry in entries:
                    if entry.key == "suivi_sections":
                        rows: list[dict[str, object]] = []
                        existing_row_map: dict[str, dict] = {}
                        try:
                            existing_rows = entry.value or []
                        except Exception:
                            existing_rows = []
                        if isinstance(existing_rows, list):
                            for existing in existing_rows:
                                if not isinstance(existing, dict):
                                    continue
                                slug = existing.get("section_slug")
                                if slug not in (None, ""):
                                    existing_row_map[str(slug)] = existing
                        if validation_targets is None:
                            validation_targets = []
                        for target in validation_targets:
                            if not section_has_status(target.slug):
                                continue
                            existing_row = existing_row_map.get(target.slug, {})
                            info = status_map.get(target.slug) or {}
                            rows.append(
                                {
                                    "section": target.title,
                                    "section_slug": target.slug,
                                    "statut": info.get("value") or default_status_value,
                                    "statut_responsable": existing_row.get("statut_responsable")
                                    or default_status_value,
                                    "reserve_message": str(existing_row.get("reserve_message") or "").strip(),
                                    "reserve_by_id": existing_row.get("reserve_by_id"),
                                    "reserve_by_display": str(existing_row.get("reserve_by_display") or "").strip(),
                                    "commentaire": info.get("commentaire") or "",
                                }
                            )
                        if existing_rows != rows:
                            entry.update_value(rows)
            parts_payload.append(
                {
                    "section_part": sub_section,
                    "entries": entries,
                    "has_drawio_table": part_has_drawio_table(entries),
                    "can_edit": False
                    if section.slug == "validation" or is_locked
                    else sub_section.can_user_edit(user),
                }
            )
        if sub_section_slug and not parts_payload:
            continue
        sections_payload.append(
            {
                "section": section,
                "parts": parts_payload,
                "can_edit": section_can_edit,
                "attachments_enabled": attachments_enabled,
                "attachments": attachments,
                "attachments_can_upload": bool(section_can_edit and attachments_enabled),
                "has_status": bool(section_status.get("has_status")),
                "status": section_status,
                "status_locked": is_locked,
                "can_update_status": bool(
                    section_status.get("has_status")
                    and user_can_update_section_status(dat, section, user)
                    and dat.status not in FINAL_DAT_STATUSES
                ),
                "validation_allowed_sections": validation_allowed_sections,
                "validation_reserve_allowed_sections": validation_reserve_allowed_sections,
                "validation_reserve_clear_allowed_sections": validation_reserve_clear_allowed_sections,
                "status_choices": status_choices,
                "status_values": {
                    "default": default_status_value,
                    "blocked": SECTION_STATUS_BLOCKED_VALUE,
                    "validated": SECTION_STATUS_VALIDATED_VALUE,
                },
            }
        )
        if sub_section_slug:
            break
    return sections_payload


def render_sub_section_snippet(dat: DAT, user, section_slug: str, sub_section_slug: str) -> str:
    payload = build_section_payload(dat, user, section_slug=section_slug, sub_section_slug=sub_section_slug)
    if not payload:
        return ""
    section_context = payload[0]
    parts = section_context.get("parts", [])
    if not parts:
        return ""
    part_context = parts[0]
    return render_to_string(
        "dat/partials/dat_sub_section_card.html",
        {
            "part": part_context,
            "container_section": section_context["section"],
            "dat": dat,
        },
    )


def is_ajax_request(request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def render_section_attachments_snippet(
    request,
    dat: DAT,
    section: DATSection,
    user,
    *,
    attachments_show_upload: bool,
) -> str:
    attachments_enabled = section_has_attachments(section.slug)
    attachments = []
    if attachments_enabled:
        attachments = list(
            DATSectionAttachment.objects.select_related("uploaded_by")
            .filter(section=section)
            .order_by("-created_at", "-id")
        )
    section_can_edit = False if section.slug == "validation" else section.can_user_edit(user)
    if section_is_locked(None, dat=dat):
        section_can_edit = False
    container = {
        "section": section,
        "attachments_enabled": attachments_enabled,
        "attachments": attachments,
        "attachments_can_upload": bool(section_can_edit and attachments_enabled),
    }
    context = {
        "container": container,
        "dat": dat,
        "attachments_show_upload": attachments_show_upload,
    }
    context.update(build_attachment_ui_context())
    return render_to_string("dat/partials/dat_section_attachments.html", context, request=request)


@login_required
@require_POST
def upload_section_attachment(request, dat_pk: int, section_slug: str):
    base_queryset = filter_dat_queryset_for_user(DAT.objects.all(), request.user)
    dat = get_object_or_404(base_queryset, pk=dat_pk)
    if dat.status in FINAL_DAT_STATUSES:
        raise PermissionDenied
    section = get_object_or_404(DATSection, dat=dat, metadata__slug=section_slug)
    if not user_can_update_section_status(dat, section, request.user):
        raise PermissionDenied
    is_ajax = is_ajax_request(request)
    redirect_url = f"{reverse('dat:my_detail', args=[dat.pk])}?section={section.slug}#section-{section.slug}"
    if not section_has_attachments(section.slug):
        if is_ajax:
            return JsonResponse(
                {
                    "success": False,
                    "messages": ["Les pieces jointes sont desactivees pour cette section."],
                    "attachments_html": render_section_attachments_snippet(
                        request,
                        dat,
                        section,
                        request.user,
                        attachments_show_upload=True,
                    ),
                }
            )
        messages.error(request, "Les pieces jointes sont desactivees pour cette section.")
        return redirect(redirect_url)
    files = request.FILES.getlist("attachments")
    if not files:
        if is_ajax:
            return JsonResponse(
                {
                    "success": False,
                    "messages": ["Aucun fichier selectionne."],
                    "attachments_html": render_section_attachments_snippet(
                        request,
                        dat,
                        section,
                        request.user,
                        attachments_show_upload=True,
                    ),
                }
            )
        messages.error(request, "Aucun fichier selectionne.")
        return redirect(redirect_url)
    saved_count = 0
    message_list = []
    for uploaded_file in files:
        try:
            create_section_attachment(section, uploaded_file, uploaded_by=request.user)
            saved_count += 1
        except ValidationError as exc:
            error_msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            if is_ajax:
                message_list.append(f"{uploaded_file.name}: {error_msg}")
            else:
                messages.error(request, f"{uploaded_file.name}: {error_msg}")
        except Exception:
            logger.exception("Erreur lors de l'upload de piece jointe (dat=%s, section=%s).", dat.pk, section.slug)
            if is_ajax:
                message_list.append(f"{uploaded_file.name}: erreur lors de l'envoi du fichier.")
            else:
                messages.error(request, f"{uploaded_file.name}: erreur lors de l'envoi du fichier.")
    if saved_count:
        if is_ajax:
            message_list.append(f"{saved_count} piece(s) jointe(s) ajoutee(s).")
        else:
            messages.success(request, f"{saved_count} piece(s) jointe(s) ajoutee(s).")
    if is_ajax:
        return JsonResponse(
            {
                "success": bool(saved_count),
                "messages": message_list,
                "attachments_html": render_section_attachments_snippet(
                    request,
                    dat,
                    section,
                    request.user,
                    attachments_show_upload=True,
                ),
            }
        )
    return redirect(redirect_url)


@login_required
def download_section_attachment(request, dat_pk: int, attachment_pk: int):
    base_queryset = filter_dat_queryset_for_user(DAT.objects.all(), request.user)
    dat = get_object_or_404(base_queryset, pk=dat_pk)
    attachment = get_object_or_404(
        DATSectionAttachment.objects.select_related("section__dat"),
        pk=attachment_pk,
        section__dat=dat,
    )
    storage = get_attachment_storage()
    try:
        file_handle = storage.open(attachment.storage_path, "rb")
    except FileNotFoundError:
        redirect_url = f"{reverse('dat:my_detail', args=[dat.pk])}?section={attachment.section.slug}"
        messages.error(request, "Le fichier demande est introuvable.")
        return redirect(redirect_url)
    download_name = build_download_filename(attachment.display_name, attachment.extension)
    response = FileResponse(
        file_handle,
        content_type=attachment.content_type or "application/octet-stream",
        as_attachment=True,
        filename=download_name,
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_POST
def remove_section_attachment(request, dat_pk: int, attachment_pk: int):
    base_queryset = filter_dat_queryset_for_user(DAT.objects.all(), request.user)
    dat = get_object_or_404(base_queryset, pk=dat_pk)
    if dat.status in FINAL_DAT_STATUSES:
        raise PermissionDenied
    attachment = get_object_or_404(
        DATSectionAttachment.objects.select_related("section__dat"),
        pk=attachment_pk,
        section__dat=dat,
    )
    if not attachment.section.can_user_edit(request.user):
        raise PermissionDenied
    is_ajax = is_ajax_request(request)
    redirect_url = f"{reverse('dat:my_detail', args=[dat.pk])}?section={attachment.section.slug}#section-{attachment.section.slug}"
    try:
        delete_section_attachment_file(attachment)
    except Exception:
        logger.exception("Erreur lors de la suppression de piece jointe (id=%s).", attachment.pk)
        if is_ajax:
            return JsonResponse(
                {
                    "success": False,
                    "messages": ["Impossible de supprimer la piece jointe."],
                    "attachments_html": render_section_attachments_snippet(
                        request,
                        dat,
                        attachment.section,
                        request.user,
                        attachments_show_upload=True,
                    ),
                }
            )
        messages.error(request, "Impossible de supprimer la piece jointe.")
        return redirect(redirect_url)
    if is_ajax:
        return JsonResponse(
            {
                "success": True,
                "messages": ["Piece jointe supprimee."],
                "attachments_html": render_section_attachments_snippet(
                    request,
                    dat,
                    attachment.section,
                    request.user,
                    attachments_show_upload=True,
                ),
            }
        )
    messages.success(request, "Piece jointe supprimee.")
    return redirect(redirect_url)


@login_required
@require_POST
def update_section_status(request, dat_pk: int, section_slug: str):
    base_queryset = filter_dat_queryset_for_user(DAT.objects.all(), request.user)
    dat = get_object_or_404(base_queryset, pk=dat_pk)
    if dat.status in FINAL_DAT_STATUSES:
        raise PermissionDenied
    section = get_object_or_404(DATSection, dat=dat, metadata__slug=section_slug)
    if sync_dat_sections_if_needed(dat):
        section = get_object_or_404(DATSection, dat=dat, metadata__slug=section_slug)
    if not section_has_status(section.slug):
        raise Http404("Section sans statut.")
    if not user_can_update_section_status(dat, section, request.user):
        raise PermissionDenied
    status_map, status_choices = build_section_status_map(dat)
    current_info = status_map.get(section.slug, {})
    new_status = request.POST.get("status")
    valid_statuses = set(status_choices.keys())
    submitted_comment = (request.POST.get("commentaire") or "").strip()
    redirect_url = f"{reverse('dat:my_detail', args=[dat.pk])}?section={section.slug}#section-{section.slug}"
    if not new_status or new_status not in valid_statuses:
        messages.error(request, "Statut invalide pour cette section.")
        return redirect(redirect_url)
    if new_status == SECTION_STATUS_BLOCKED_VALUE and not submitted_comment:
        messages.error(request, "Un commentaire est obligatoire pour bloquer une section.")
        return redirect(redirect_url)
    if new_status == current_info.get("value"):
        messages.info(request, "Le statut de la section est déjà à jour.")
        return redirect(redirect_url)
    status_part = _find_section_status_part(dat)
    if status_part is None:
        messages.error(request, "Impossible de mettre à jour le statut de cette section.")
        return redirect(redirect_url)
    default_status = _default_status_value(status_choices)
    try:
        raw_rows = status_part.value or []
    except Exception:
        raw_rows = []
    existing_row_map: dict[str, dict] = {}
    if isinstance(raw_rows, list):
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            slug = row.get("section_slug")
            if slug not in (None, ""):
                existing_row_map[str(slug)] = row
    sections = list(dat.sections.order_by("order", "id").select_related("metadata"))
    updated_rows = []
    validated_value = SECTION_STATUS_VALIDATED_VALUE
    confirm_reset = request.POST.get("confirm_responsable_reset") == "1"
    current_row_for_section = existing_row_map.get(section.slug, {})
    current_responsable_value = current_row_for_section.get("statut_responsable") or default_status
    target_reserve_message = str(current_row_for_section.get("reserve_message") or "").strip()
    target_reserve_by_id = current_row_for_section.get("reserve_by_id")
    reserve_message = target_reserve_message
    reserve_by_id = target_reserve_by_id
    if (
        current_info.get("value") == validated_value
        and new_status != validated_value
        and current_responsable_value == validated_value
        and not confirm_reset
    ):
        messages.error(
            request,
            "Cette section a une validation responsable. Confirmez la dévalidation pour la réinitialiser.",
        )
        return redirect(redirect_url)
    for item in sections:
        if not section_has_status(item.slug):
            continue
        existing = status_map.get(item.slug, {})
        comment = existing.get("commentaire", "")
        status_value = existing.get("value") or default_status
        if item.slug == section.slug:
            status_value = new_status
            if new_status == SECTION_STATUS_BLOCKED_VALUE:
                comment = submitted_comment
            else:
                comment = ""
        existing_row = existing_row_map.get(item.slug, {})
        responsable_value = existing_row.get("statut_responsable") or default_status
        if item.slug == section.slug and current_responsable_value == validated_value and new_status != validated_value:
            responsable_value = default_status
        reserve_message = str(existing_row.get("reserve_message") or "").strip()
        reserve_by_id = existing_row.get("reserve_by_id")
        reserve_by_display = str(existing_row.get("reserve_by_display") or "").strip()
        if not reserve_message:
            reserve_by_id = None
            reserve_by_display = ""
        updated_rows.append(
            {
                "section": item.title,
                "section_slug": item.slug,
                "statut": status_value,
                "statut_responsable": responsable_value,
                "reserve_message": reserve_message,
                "reserve_by_id": reserve_by_id,
                "reserve_by_display": reserve_by_display,
                "commentaire": comment or "",
            }
        )
    status_part.update_value(updated_rows)
    target_label = status_choices.get(new_status, new_status)
    refresh_dat_status(dat, actor=request.user, force_in_progress=True)
    if new_status == validated_value and target_reserve_message and target_reserve_by_id:
        if target_reserve_by_id != getattr(request.user, "id", None):
            reserve_user = get_user_model().objects.filter(pk=target_reserve_by_id).first()
            if reserve_user:
                validator_display = format_user_display(request.user)
                target_url = f"{reverse('dat:my_detail', args=[dat.pk])}?section={section.slug}#section-{section.slug}"
                create_user_notification(
                    reserve_user,
                    title="Réserve à lever",
                    message=(
                        f"{validator_display} a validé la section « {section.title} ».\n\n"
                        f"Message de réserve : {target_reserve_message}\n\n"
                        "Vous pouvez lever la réserve si tout est conforme."
                    ),
                    level="info",
                    dat=dat,
                    target_url=target_url,
                    created_by=request.user,
                    created_by_display=validator_display,
                    extra_data={
                        "section_slug": section.slug,
                        "section_title": section.title,
                        "reserve_message": target_reserve_message,
                    },
                )
    messages.success(request, f"Statut mis à jour : {target_label}.")
    return redirect(redirect_url)


@login_required
@require_POST
def update_section_responsible_status(request, dat_pk: int, section_slug: str):
    base_queryset = filter_dat_queryset_for_user(DAT.objects.all(), request.user)
    dat = get_object_or_404(base_queryset, pk=dat_pk)
    if dat.status in FINAL_DAT_STATUSES:
        raise PermissionDenied
    section = get_object_or_404(DATSection, dat=dat, metadata__slug=section_slug)
    sync_dat_sections_if_needed(dat)
    if not section_has_status(section.slug):
        raise Http404("Section sans statut.")
    try:
        participants = list(dat.participants.select_related("user__business_group__responsible").all())
    except Exception:
        participants = []
    dat._participants_cache = participants  # type: ignore[attr-defined]
    if not (user_is_dat_admin(request.user) or user_is_responsible_for_section(dat, section, request.user, participants=participants)):
        raise PermissionDenied

    status_map, status_choices = build_section_status_map(dat)
    section_info = status_map.get(section.slug) or {}
    if section_info.get("value") != SECTION_STATUS_VALIDATED_VALUE:
        messages.error(request, "La section doit être validée avant validation responsable.")
        return redirect(f"{reverse('dat:my_detail', args=[dat.pk])}?section={section.slug}#section-{section.slug}")
    new_status = request.POST.get("status")
    valid_statuses = set(status_choices.keys())
    redirect_url = f"{reverse('dat:my_detail', args=[dat.pk])}?section=validation#section-validation"
    if not new_status or new_status not in valid_statuses:
        messages.error(request, "Statut invalide pour cette section.")
        return redirect(redirect_url)

    status_part = _find_section_status_part(dat)
    if status_part is None:
        messages.error(request, "Impossible de mettre à jour le statut de cette section.")
        return redirect(redirect_url)
    default_status = _default_status_value(status_choices)
    try:
        raw_rows = status_part.value or []
    except Exception:
        raw_rows = []
    existing_row_map: dict[str, dict] = {}
    if isinstance(raw_rows, list):
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            slug = row.get("section_slug")
            if slug not in (None, ""):
                existing_row_map[str(slug)] = row
            label = row.get("section")
            if label not in (None, "") and str(label) not in existing_row_map:
                existing_row_map[str(label)] = row
    current_row = existing_row_map.get(section.slug) or existing_row_map.get(section.title) or {}
    current_value = current_row.get("statut_responsable") or default_status
    if current_value == SECTION_STATUS_VALIDATED_VALUE and new_status != current_value:
        messages.error(request, "Cette validation est déjà faite et ne peut plus changer de statut.")
        return redirect(redirect_url)
    if new_status == current_value:
        messages.info(request, "Le statut de validation est déjà à jour.")
        return redirect(redirect_url)

    sections = list(dat.sections.order_by("order", "id").select_related("metadata"))
    updated_rows: list[dict[str, object]] = []
    for item in sections:
        if not section_has_status(item.slug):
            continue
        existing = existing_row_map.get(item.slug) or existing_row_map.get(item.title) or {}
        assignee_value = existing.get("statut") or (status_map.get(item.slug) or {}).get("value") or default_status
        comment = existing.get("commentaire") or (status_map.get(item.slug) or {}).get("commentaire") or ""
        manager_value = existing.get("statut_responsable") or default_status
        if item.slug == section.slug:
            manager_value = new_status
        reserve_message = str(existing.get("reserve_message") or "").strip()
        reserve_by_id = existing.get("reserve_by_id")
        reserve_by_display = str(existing.get("reserve_by_display") or "").strip()
        if not reserve_message:
            reserve_by_id = None
            reserve_by_display = ""
        updated_rows.append(
            {
                "section": item.title,
                "section_slug": item.slug,
                "statut": assignee_value,
                "statut_responsable": manager_value,
                "reserve_message": reserve_message,
                "reserve_by_id": reserve_by_id,
                "reserve_by_display": reserve_by_display,
                "commentaire": comment,
            }
        )
    status_part.update_value(updated_rows)
    actor = request.user if getattr(request.user, "is_authenticated", False) else None
    DATHistory.objects.create(
        dat=dat,
        action=DATHistoryAction.RESPONSIBLE_VALIDATION,
        performed_by=actor,
        performed_by_display=format_user_display(actor),
        details={
            "section": {"slug": section.slug, "title": section.title},
            "from": status_choices.get(current_value, current_value),
            "to": status_choices.get(new_status, new_status),
        },
    )
    refresh_dat_status(dat, actor=request.user)
    target_label = status_choices.get(new_status, new_status)
    messages.success(request, f"Validation responsable mise à jour : {target_label}.")
    return redirect(redirect_url)


@login_required
@require_POST
def update_section_reserve(request, dat_pk: int, section_slug: str):
    base_queryset = filter_dat_queryset_for_user(DAT.objects.all(), request.user)
    dat = get_object_or_404(base_queryset, pk=dat_pk)
    if dat.status in FINAL_DAT_STATUSES:
        raise PermissionDenied
    section = get_object_or_404(DATSection, dat=dat, metadata__slug=section_slug)
    sync_dat_sections_if_needed(dat)
    if section.slug == "validation" or not section_has_status(section.slug):
        raise Http404("Section sans statut.")
    reserve_message = (request.POST.get("reserve_message") or "").strip()
    if not reserve_message:
        messages.error(request, "Un message est obligatoire pour mettre une réserve.")
        return redirect(f"{reverse('dat:my_detail', args=[dat.pk])}?section=validation#section-validation")

    try:
        participants = list(dat.participants.select_related("role", "user__business_group__responsible").all())
    except Exception:
        participants = []
    user_id = getattr(request.user, "id", None)
    is_any_group_responsible = user_is_dat_admin(request.user) or any(
        getattr(getattr(getattr(p, "user", None), "business_group", None), "responsible_id", None) == user_id
        for p in participants
    )
    if not is_any_group_responsible:
        raise PermissionDenied
    if not user_is_dat_admin(request.user) and user_is_responsible_for_section(dat, section, request.user, participants=participants):
        raise PermissionDenied

    status_map, status_choices = build_section_status_map(dat)
    status_part = _find_section_status_part(dat)
    if status_part is None:
        messages.error(request, "Impossible de mettre une réserve sur cette section.")
        return redirect(f"{reverse('dat:my_detail', args=[dat.pk])}?section=validation#section-validation")
    default_status = _default_status_value(status_choices)
    try:
        raw_rows = status_part.value or []
    except Exception:
        raw_rows = []
    existing_row_map: dict[str, dict] = {}
    if isinstance(raw_rows, list):
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            slug = row.get("section_slug")
            if slug not in (None, ""):
                existing_row_map[str(slug)] = row
            label = row.get("section")
            if label not in (None, "") and str(label) not in existing_row_map:
                existing_row_map[str(label)] = row
    current_row = existing_row_map.get(section.slug) or existing_row_map.get(section.title) or {}
    existing_reserve_message = str(current_row.get("reserve_message") or "").strip()
    existing_reserve_by_id = current_row.get("reserve_by_id")
    if existing_reserve_message and existing_reserve_by_id != user_id:
        raise PermissionDenied

    reserve_by_display = format_user_display(request.user)
    sections = list(dat.sections.order_by("order", "id").select_related("metadata"))
    updated_rows: list[dict[str, object]] = []
    for item in sections:
        if not section_has_status(item.slug):
            continue
        existing = existing_row_map.get(item.slug) or existing_row_map.get(item.title) or {}
        info = status_map.get(item.slug) or {}
        assignee_value = existing.get("statut") or info.get("value") or default_status
        responsable_value = existing.get("statut_responsable") or info.get("responsable_value") or default_status
        comment = existing.get("commentaire") or info.get("commentaire") or ""
        reserve_msg = str(existing.get("reserve_message") or "").strip()
        reserve_by_id = existing.get("reserve_by_id")
        reserve_by_display_existing = str(existing.get("reserve_by_display") or "").strip()
        if item.slug == section.slug:
            assignee_value = default_status
            responsable_value = default_status
            reserve_msg = reserve_message
            reserve_by_id = user_id
            reserve_by_display_existing = reserve_by_display
        if not reserve_msg:
            reserve_by_id = None
            reserve_by_display_existing = ""
        updated_rows.append(
            {
                "section": item.title,
                "section_slug": item.slug,
                "statut": assignee_value,
                "statut_responsable": responsable_value,
                "reserve_message": reserve_msg,
                "reserve_by_id": reserve_by_id,
                "reserve_by_display": reserve_by_display_existing,
                "commentaire": comment,
            }
        )
    status_part.update_value(updated_rows)
    refresh_dat_status(dat, actor=request.user, force_in_progress=True)
    DATReserveHistory.objects.create(
        dat=dat,
        section_slug=section.slug,
        section_title=section.title,
        action=DATReserveHistoryAction.SET,
        reserve_message=reserve_message,
        reserved_by=request.user if getattr(request.user, "is_authenticated", False) else None,
        reserved_by_display=reserve_by_display,
    )

    try:
        allowed_role_ids = set(section.allowed_roles.values_list("pk", flat=True))
    except Exception:
        allowed_role_ids = set()
    recipients = []
    seen_user_ids: set[int] = set()
    for participant in participants:
        if getattr(participant, "role_id", None) not in allowed_role_ids:
            continue
        recipient = getattr(participant, "user", None)
        recipient_id = getattr(recipient, "id", None)
        if recipient_id and recipient_id not in seen_user_ids:
            seen_user_ids.add(int(recipient_id))
            recipients.append(recipient)
        group = getattr(recipient, "business_group", None) if recipient is not None else None
        responsible = getattr(group, "responsible", None) if group is not None else None
        responsible_id = getattr(responsible, "id", None)
        if responsible_id and responsible_id not in seen_user_ids:
            seen_user_ids.add(int(responsible_id))
            recipients.append(responsible)
    target_url = f"{reverse('dat:my_detail', args=[dat.pk])}?section={section.slug}#section-{section.slug}"
    for recipient in recipients:
        if getattr(recipient, "id", None) == getattr(request.user, "id", None):
            continue
        create_user_notification(
            recipient,
            title="Réserve sur votre section",
            message=(
                f"{reserve_by_display} a mis une réserve sur la section « {section.title} ».\n\n"
                f"Message : {reserve_message}\n\n"
                "Votre section attend des modifications."
            ),
            level="warning",
            dat=dat,
            target_url=target_url,
            created_by=request.user,
            created_by_display=reserve_by_display,
            extra_data={"section_slug": section.slug, "section_title": section.title, "reserve_message": reserve_message},
        )
    messages.success(request, "Réserve enregistrée et notification envoyée.")
    return redirect(f"{reverse('dat:my_detail', args=[dat.pk])}?section=validation#section-validation")


@login_required
@require_POST
def clear_section_reserve(request, dat_pk: int, section_slug: str):
    base_queryset = filter_dat_queryset_for_user(DAT.objects.all(), request.user)
    dat = get_object_or_404(base_queryset, pk=dat_pk)
    section = get_object_or_404(DATSection, dat=dat, metadata__slug=section_slug)
    sync_dat_sections_if_needed(dat)
    if section.slug == "validation" or not section_has_status(section.slug):
        raise Http404("Section sans statut.")

    status_part = _find_section_status_part(dat)
    if status_part is None:
        messages.error(request, "Impossible de lever la réserve sur cette section.")
        return redirect(f"{reverse('dat:my_detail', args=[dat.pk])}?section=validation#section-validation")
    status_map, status_choices = build_section_status_map(dat)
    default_status = _default_status_value(status_choices)
    try:
        raw_rows = status_part.value or []
    except Exception:
        raw_rows = []
    existing_row_map: dict[str, dict] = {}
    if isinstance(raw_rows, list):
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            slug = row.get("section_slug")
            if slug not in (None, ""):
                existing_row_map[str(slug)] = row
            label = row.get("section")
            if label not in (None, "") and str(label) not in existing_row_map:
                existing_row_map[str(label)] = row
    current_row = existing_row_map.get(section.slug) or existing_row_map.get(section.title) or {}
    reserve_by_id = current_row.get("reserve_by_id")
    current_reserve_message = str(current_row.get("reserve_message") or "").strip()
    if reserve_by_id != getattr(request.user, "id", None):
        raise PermissionDenied

    sections = list(dat.sections.order_by("order", "id").select_related("metadata"))
    updated_rows: list[dict[str, object]] = []
    for item in sections:
        if not section_has_status(item.slug):
            continue
        existing = existing_row_map.get(item.slug) or existing_row_map.get(item.title) or {}
        info = status_map.get(item.slug) or {}
        assignee_value = existing.get("statut") or info.get("value") or default_status
        responsable_value = existing.get("statut_responsable") or info.get("responsable_value") or default_status
        comment = existing.get("commentaire") or info.get("commentaire") or ""
        reserve_msg = str(existing.get("reserve_message") or "").strip()
        reserve_by_id_existing = existing.get("reserve_by_id")
        reserve_by_display_existing = str(existing.get("reserve_by_display") or "").strip()
        if item.slug == section.slug:
            reserve_msg = ""
            reserve_by_id_existing = None
            reserve_by_display_existing = ""
        if not reserve_msg:
            reserve_by_id_existing = None
            reserve_by_display_existing = ""
        updated_rows.append(
            {
                "section": item.title,
                "section_slug": item.slug,
                "statut": assignee_value,
                "statut_responsable": responsable_value,
                "reserve_message": reserve_msg,
                "reserve_by_id": reserve_by_id_existing,
                "reserve_by_display": reserve_by_display_existing,
                "commentaire": comment,
            }
        )
    status_part.update_value(updated_rows)
    DATReserveHistory.objects.create(
        dat=dat,
        section_slug=section.slug,
        section_title=section.title,
        action=DATReserveHistoryAction.CLEARED,
        reserve_message=current_reserve_message,
        reserved_by=request.user if getattr(request.user, "is_authenticated", False) else None,
        reserved_by_display=format_user_display(request.user),
    )
    messages.success(request, "Réserve levée.")
    return redirect(f"{reverse('dat:my_detail', args=[dat.pk])}?section=validation#section-validation")


@login_required
@require_POST
def submit_validation_decision(request, pk: int):
    base_queryset = filter_dat_queryset_for_user(
        DAT.objects.select_related("application", "owner").prefetch_related("participants__role"),
        request.user,
    )
    dat = get_object_or_404(base_queryset, pk=pk)
    if dat.status != DATStatus.EN_ATTENTE_DE_REVUE:
        messages.error(request, "Ce DAT n'est pas en attente de revue.")
        return redirect(reverse("dat:my_detail", args=[dat.pk]))
    if not user_can_review_dat(dat, request.user):
        raise PermissionDenied

    decision_value = request.POST.get("decision")
    valid_targets = {DATStatus.VALIDER, DATStatus.REFUSE, DATStatus.RESERVE}
    try:
        target_status = DATStatus(decision_value)
    except Exception:
        target_status = None
    if target_status not in valid_targets:
        messages.error(request, "Décision de validation invalide.")
        return redirect(reverse("dat:my_detail", args=[dat.pk]))

    status_map, status_choices = build_section_status_map(dat)
    if target_status == DATStatus.RESERVE:
        reset_section_statuses_to_default(dat, status_map=status_map, status_choices=status_choices)

    dat.status = target_status
    dat._history_actor = request.user  # type: ignore[attr-defined]
    dat.save(update_fields=["status", "updated_at"])

    label = dat.get_status_display()
    if target_status in FINAL_DAT_STATUSES:
        messages.success(request, f"Le DAT est maintenant clôturé ({label}).")
    else:
        messages.success(request, f"Le DAT est placé en réserve ({label}). Les sections sont à nouveau éditables.")

    return redirect(reverse("dat:my_detail", args=[dat.pk]))


def user_is_porteur_demande(user):
    is_role = getattr(user, "is_role", None)
    return bool(callable(is_role) and is_role(PORTEUR_ROLE_SLUG))


def user_can_create_dat_entities(user):
    is_authenticated = getattr(user, "is_authenticated", False)
    return bool(is_authenticated and user_is_porteur_demande(user))


def user_can_manage_dat(user):
    if user is None:
        return False
    is_role = getattr(user, "is_role", None)
    return (
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or (callable(is_role) and is_role("admin"))
    )


def get_next_status(current_status: str) -> str | None:
    if current_status == DATStatus.NOUVELLE_DEMANDE:
        return DATStatus.EN_COURS
    if current_status in (DATStatus.EN_COURS, DATStatus.RESERVE):
        return DATStatus.EN_ATTENTE_DE_REVUE
    return None


def user_can_progress_dat(dat: DAT, user) -> bool:
    # Manual progression is disabled; status changes are automatic or handled via the validation section.
    return False


class BaseSecuredViewSet(LoginRequiredMixin, ModelViewSet):
    list_view_class = ModuleAwareListView
    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated

    def _can_mutate(self, request):
        return user_can_manage_dat(request.user)

    def _can_add(self, request):
        return self._can_mutate(request)

    def has_add_permission(self, request):
        return self._can_add(request)

    def has_change_permission(self, request, obj=None):
        return self._can_mutate(request)

    def has_delete_permission(self, request, obj=None):
        return self._can_mutate(request)


class DATCreateView(ModuleContextMixin, CreateModelView):
    template_name = "dat/dat_form.html"
    success_url = reverse_lazy("dat:my_list")

    def dispatch(self, request, *args, **kwargs):
        if not user_can_create_dat_entities(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Le DAT a été créé avec succès.")
        return response

    def get_success_url(self):
        if user_can_manage_dat(self.request.user):
            return reverse("dat:admin_list")
        return super().get_success_url()


class DATUpdateView(ModuleContextMixin, UpdateModelView):
    template_name = "dat/dat_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class DATDetailView(LoginRequiredMixin, ModuleContextMixin, DetailModelView):
    model = DAT
    template_name = "dat/dat_detail.html"

    def has_view_permission(self, request, obj=None):
        return bool(getattr(request.user, "is_authenticated", False))

    def get_queryset(self):
        base_queryset = (
            DAT.objects.select_related(
                "application",
                "application__business_direction",
                "business_direction",
                "owner",
            )
            .prefetch_related(
                HISTORY_ENTRIES_PREFETCH,
                RESERVE_HISTORY_ENTRIES_PREFETCH,
                "participants__role",
                "participants__user",
            )
        )
        return filter_dat_queryset_for_user(base_queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["history_entries"] = get_dat_history_entries(self.object)
        context["history_actions"] = DATHistoryAction
        context["reserve_history_entries"] = get_dat_reserve_history_entries(self.object)
        context["reserve_validation_history_entries"] = build_dat_reserve_validation_history(self.object)
        context["dat_history_user_choices"] = build_dat_history_user_choices(self.object)
        context["participant_overview"] = build_participant_overview(self.object)
        context["current_responsibles"] = get_current_responsibles(self.object)
        context["sections_payload"] = build_section_payload(self.object, self.request.user)
        context["section_nav"] = list(
            self.object.sections.order_by("order", "id").values(
                slug=F("metadata__slug"),
                title=F("metadata__title"),
            )
        )
        context["can_review_dat"] = user_can_review_dat(self.object, self.request.user)
        context.update(build_attachment_ui_context())
        context["attachments_show_upload"] = False
        return context


def dat_crud_detail_unavailable(request, pk):
    return DATDetailView.as_view()(request, pk=pk)


class DATViewSet(BaseSecuredViewSet):
    model = DAT
    queryset = None
    paginate_by = None
    form_class = DATForm
    create_view_class = DATCreateView
    update_view_class = DATUpdateView
    detail_view_class = DATDetailView

    def _can_add(self, request):
        return user_can_create_dat_entities(request.user)

    list_display = ("reference", "title", "application", "business_direction", "status", "owner", "created_at")
    list_display_links = ("reference",)
    ordering = ("-created_at",)
    search_fields = ("reference", "title", "description", "application__name", "application__code", "business_direction__name")

    layout = Layout(
        Fieldset("Identite", Row("reference", "title"), Row("application")),
        Fieldset(
            "Participants",
            Row("participant_porteur_demande"),
            Row("participant_architecte_referent", "participant_architecte_technique"),
            Row("participant_urbaniste", "participant_analyste_secu"),
            Row("participant_rssi", "participant_comite_validation"),
            Row("participant_infra_exploitation"),
        ),
        Fieldset("Contenu", Row("description")),
        Fieldset("Flux", Row("status", "owner")),
    )

    def get_queryset(self, request):
        base_queryset = (
            DAT.objects.select_related("application", "application__business_direction", "business_direction", "owner")
            .order_by("-created_at")
        )
        return filter_dat_queryset_for_user(base_queryset, request.user)


class ApplicationCreateView(ModuleContextMixin, CreateModelView):
    def dispatch(self, request, *args, **kwargs):
        if not user_can_create_dat_entities(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class ApplicationUpdateView(ModuleContextMixin, UpdateModelView):
    pass


class ApplicationDetailView(ModuleContextMixin, DetailModelView):
    pass


class ApplicationViewSet(BaseSecuredViewSet):
    model = Application
    queryset = Application.objects.all()
    paginate_by = None
    list_view_class = ApplicationListView
    create_view_class = ApplicationCreateView
    update_view_class = ApplicationUpdateView
    detail_view_class = ApplicationDetailView

    def _can_add(self, request):
        return user_can_create_dat_entities(request.user)

    list_display = ("code", "name", "business_direction", "formatted_created_at", "formatted_updated_at")
    list_display_links = ("code",)
    ordering = ("name",)
    search_fields = ("code", "name", "description", "business_direction__name")

    form_fields = ["code", "name", "business_direction", "description"]
    layout = Layout(
        Fieldset("Identite", Row("code", "name"), Row("business_direction")),
        Fieldset("Description", Row("description")),
    )


class DatList(ModuleContextMixin, LoginRequiredMixin, ListView):
    model = DAT
    template_name = "dat/dat_list.html"
    context_object_name = "object_list"
    paginate_by = 10

    owner_editable_statuses = OWNER_EDITABLE_STATUSES

    def get_queryset(self):
        self.raw_search_query = self.request.GET.get("q", "")
        cleaned_query = self.raw_search_query.strip()
        self.search_query = cleaned_query if len(cleaned_query) >= 3 else ""
        self.search_too_short = bool(cleaned_query and not self.search_query)
        self.application_filter = self.request.GET.get("application", "").strip()
        try:
            self.application_filter_id = int(self.application_filter) if self.application_filter else None
        except (TypeError, ValueError):
            self.application_filter_id = None
        base_queryset = (
            DAT.objects.select_related("application", "application__business_direction", "business_direction", "owner")
            .order_by("-created_at")
        )
        self.base_queryset_for_filters = filter_dat_queryset_for_user(base_queryset, self.request.user)
        queryset = self.base_queryset_for_filters
        if self.search_query:
            queryset = queryset.filter(
                Q(reference__icontains=self.search_query)
                | Q(title__icontains=self.search_query)
            )
        if self.application_filter_id:
            queryset = queryset.filter(application_id=self.application_filter_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["owner_editable_statuses"] = {status.value for status in self.owner_editable_statuses}
        user = self.request.user
        context["owner_can_edit"] = user_is_dat_admin(user)
        context["can_create_dat"] = user_can_create_dat_entities(user)
        search_query = getattr(self, "search_query", "")
        context["search_query"] = getattr(self, "raw_search_query", "")
        context["search_too_short"] = getattr(self, "search_too_short", False)
        context["application_filter"] = getattr(self, "application_filter", "")
        base_queryset = getattr(self, "base_queryset_for_filters", None)
        if base_queryset is None:
            base_queryset = filter_dat_queryset_for_user(
                DAT.objects.select_related("application").all(),
                self.request.user,
            )
        context["application_choices"] = (
            Application.objects.filter(dats__in=base_queryset)
            .distinct()
            .order_by("name")
        )
        base_params = {}
        if search_query:
            base_params["q"] = search_query
        if getattr(self, "application_filter_id", None):
            base_params["application"] = self.application_filter_id
        context["base_querystring"] = urlencode(base_params)
        return context


class DatDetail(ModuleContextMixin, LoginRequiredMixin, DetailView):
    model = DAT
    template_name = "dat/my_dat_detail.html"
    context_object_name = "dat"

    def get_queryset(self):
        base_queryset = (
            DAT.objects.select_related("application", "owner")
            .prefetch_related(
                HISTORY_ENTRIES_PREFETCH,
                RESERVE_HISTORY_ENTRIES_PREFETCH,
                "participants__role",
                "participants__user",
            )
        )
        return filter_dat_queryset_for_user(base_queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["history_entries"] = get_dat_history_entries(self.object)
        context["history_actions"] = DATHistoryAction
        context["reserve_history_entries"] = get_dat_reserve_history_entries(self.object)
        context["reserve_validation_history_entries"] = build_dat_reserve_validation_history(self.object)
        context["dat_history_user_choices"] = build_dat_history_user_choices(self.object)
        context["owner_editable_statuses"] = {status.value for status in OWNER_EDITABLE_STATUSES}
        context["owner_can_edit"] = user_is_dat_admin(self.request.user)
        context["can_create_dat"] = user_can_create_dat_entities(self.request.user)
        next_status = get_next_status(self.object.status)
        context["next_status"] = next_status
        context["next_status_label"] = DATStatus(next_status).label if next_status else None
        context["can_progress_dat"] = user_can_progress_dat(self.object, self.request.user)
        context["export_urls"] = {
            "pdf_trigger": reverse("dat:my_export_pdf_trigger", args=[self.object.pk]),
            "pdf_download": reverse("dat:my_export_pdf_download", args=[self.object.pk]),
            "json": reverse("dat:my_export_json", args=[self.object.pk]),
            "status": reverse("dat:my_export_pdf_status", args=[self.object.pk]),
        }
        context["pdf_export_available"] = dat_pdf_export_exists(self.object)
        context["pdf_export_generated_at"] = dat_pdf_export_modified_at(self.object)
        context["pdf_export_in_progress"] = self.object.pdf_export_in_progress
        context["pdf_export_requested_at"] = self.object.pdf_export_requested_at
        context["pdf_export_requested_by_display"] = self.object.pdf_export_requested_by_display
        sync_dat_sections_if_needed(self.object)
        context.update(build_dat_overview_context(self.object, self.request.user))
        context.update(build_attachment_ui_context())
        context["attachments_show_upload"] = True
        section_nav = list(
            self.object.sections.order_by("order", "id").values(
                slug=F("metadata__slug"),
                title=F("metadata__title"),
            )
        )
        section_status_map, section_status_choices = build_section_status_map(self.object)
        context["section_status_map"] = section_status_map
        context["section_status_choices"] = section_status_choices
        valid_slugs = {entry["slug"] for entry in section_nav}
        default_slug = (
            "informations-generales"
            if "informations-generales" in valid_slugs
            else (section_nav[0]["slug"] if section_nav else None)
        )
        requested_slug = self.request.GET.get("section")
        selected_slug = requested_slug or default_slug
        invalid_section = False
        if requested_slug:
            if requested_slug == "overview" and "informations-generales" in valid_slugs:
                selected_slug = "informations-generales"
            elif requested_slug not in valid_slugs:
                selected_slug = default_slug
                invalid_section = True
        if selected_slug not in valid_slugs:
            selected_slug = default_slug
        if invalid_section:
            messages.warning(
                self.request,
                "La section demandée est introuvable.",
            )
        context["section_nav"] = section_nav
        context["selected_section_slug"] = selected_slug
        context["selected_sections"] = (
            build_section_payload(
                self.object,
                self.request.user,
                section_slug=selected_slug,
                section_status_map=section_status_map,
                section_status_choices=section_status_choices,
            )
            if selected_slug
            else []
        )
        return context


class DatExportBaseView(LoginRequiredMixin, View):
    http_method_names = ["get"]
    template_name = "dat/exports/dat_export_pdf.html"

    def get_queryset(self):
        base_queryset = (
            DAT.objects.select_related("application", "owner")
            .prefetch_related("participants__role", "participants__user")
        )
        return filter_dat_queryset_for_user(base_queryset, self.request.user)

    def get_object(self):
        queryset = self.get_queryset()
        return get_object_or_404(queryset, pk=self.kwargs.get("pk"))

    def build_filename(self, dat: DAT, extension: str) -> str:
        base = slugify(dat.reference or dat.title or "") or f"dat-{dat.pk}"
        return f"{base}.{extension}"

    def build_pdf_document(self, dat: DAT):
        base_url = self.request.build_absolute_uri("/")
        return generate_dat_pdf(dat, base_url=base_url)


class DatExportJSONView(DatExportBaseView):
    def get(self, request, *args, **kwargs):
        dat = self.get_object()
        builder = get_dat_export_model_builder()
        payload = builder.build(dat)
        response = JsonResponse(
            payload,
            json_dumps_params={"ensure_ascii": False, "indent": 2},
        )
        response["Content-Disposition"] = f'attachment; filename="{self.build_filename(dat, "json")}"'
        return response


class DatGeneratePDFExportView(DatExportBaseView):
    def get(self, request, *args, **kwargs):
        dat = self.get_object()
        pdf_content, _payload = self.build_pdf_document(dat)
        try:
            store_dat_pdf_export(dat, pdf_content)
        except Exception as exc:  # pragma: no cover - storage failure should be surfaced
            logger.warning("Impossible d'enregistrer l'export PDF du DAT %s: %s", dat.pk, exc)
        response = HttpResponse(pdf_content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{self.build_filename(dat, "pdf")}"'
        return response


class DatTriggerPDFExportView(DatExportBaseView):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        dat = self.get_object()
        base_url = request.build_absolute_uri("/")
        scheduled = schedule_dat_pdf_generation(dat, request.user, base_url=base_url)
        if scheduled:
            requester = format_user_display(request.user) if request.user.is_authenticated else "Système"
            messages.success(
                request,
                f"Une génération PDF a été lancée par {requester}. Vous serez informé lorsque le document sera prêt.",
            )
        else:
            messages.warning(
                request,
                "Une génération PDF est déjà en cours pour ce DAT.",
            )
        return redirect("dat:my_detail", pk=dat.pk)


class DatDownloadCachedPDFView(DatExportBaseView):
    def get(self, request, *args, **kwargs):
        dat = self.get_object()
        file_handle = open_dat_pdf_export(dat)
        if file_handle is None:
            messages.warning(
                request,
                "Aucun export PDF n'est disponible pour ce DAT. Veuillez en générer un nouveau.",
            )
            return redirect("dat:my_detail", pk=dat.pk)
        response = FileResponse(file_handle, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{self.build_filename(dat, "pdf")}"'
        return response


class DatExportStatusView(DatExportBaseView):
    def get(self, request, *args, **kwargs):
        dat = self.get_object()
        generated_at = dat_pdf_export_modified_at(dat)
        payload = {
            "in_progress": dat.pdf_export_in_progress,
            "requested_at": isoformat_datetime(dat.pdf_export_requested_at),
            "requested_at_display": localize_datetime(dat.pdf_export_requested_at)
            if dat.pdf_export_requested_at
            else None,
            "requested_by": dat.pdf_export_requested_by_display,
            "available": dat_pdf_export_exists(dat),
            "generated_at": isoformat_datetime(generated_at),
            "generated_at_display": localize_datetime(generated_at) if generated_at else None,
        }
        return JsonResponse(payload)


class DatSubSectionUpdateView(ModuleContextMixin, LoginRequiredMixin, FormView):
    template_name = "dat/dat_sub_section_form.html"
    form_class = DATSubSectionForm

    def dispatch(self, request, *args, **kwargs):
        dat_pk = kwargs.get("dat_pk")
        section_slug = kwargs.get("section_slug")
        sub_section_slug = kwargs.get("sub_section_slug")
        try:
            base_queryset = DATSubSection.objects.select_related("section__dat").prefetch_related("allowed_roles")
            self.sub_section = get_object_or_404(
                base_queryset,
                section__dat_id=dat_pk,
                section__metadata__slug=section_slug,
                slug=sub_section_slug,
            )
            self.section = self.sub_section.section
            dat = self.section.dat
            if dat.status in FINAL_DAT_STATUSES:
                raise PermissionDenied
            if sync_dat_sections_if_needed(self.section.dat):
                self.sub_section = get_object_or_404(
                    base_queryset,
                    section__dat_id=dat_pk,
                    section__metadata__slug=section_slug,
                    slug=sub_section_slug,
                )
                self.section = self.sub_section.section
            if not self.sub_section.can_user_edit(request.user):
                raise PermissionDenied
            status_map, _choices = build_section_status_map(self.section.dat)
            if section_is_locked(status_map.get(self.section.slug), dat=self.section.dat):
                raise PermissionDenied
        except (Http404, PermissionDenied):
            raise
        except Exception:
            logger.exception(
                "Failed to load DAT sub-section edit form",
                extra={
                    "dat_id": dat_pk,
                    "section_slug": section_slug,
                    "sub_section_slug": sub_section_slug,
                    "user_id": getattr(request.user, "id", None),
                },
            )
            raise
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["sub_section"] = self.sub_section
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sub_section"] = self.sub_section
        context["section"] = self.section
        context["dat"] = self.section.dat
        context["form_action"] = self.request.path
        return context

    def is_ajax(self) -> bool:
        return self.request.headers.get("x-requested-with") == "XMLHttpRequest"

    def form_valid(self, form):
        changes = form.save()
        dat = self.section.dat
        if changes:
            actor = self.request.user if self.request.user.is_authenticated else None
            actor_display = format_user_display(actor) if actor else ""
            DATHistory.objects.create(
                dat=dat,
                action=DATHistoryAction.SECTION_UPDATED,
                performed_by=actor,
                performed_by_display=actor_display,
                details={
                    "section": {
                        "slug": self.section.slug,
                        "title": self.section.title,
                    },
                    "sub_section": {
                        "slug": self.sub_section.slug,
                        "title": self.sub_section.title,
                    },
                    "changes": changes,
                },
            )
            message = f"La sous-section « {self.sub_section.title} » a été mise à jour."
            if not self.is_ajax():
                messages.success(self.request, message)
        else:
            message = "Aucune modification détectée sur cette sous-section."
            if not self.is_ajax():
                messages.info(self.request, message)
        refresh_dat_status(dat, actor=self.request.user, force_in_progress=bool(changes))
        if self.is_ajax():
            html = render_sub_section_snippet(
                dat,
                self.request.user,
                self.section.slug,
                self.sub_section.slug,
            )
            return JsonResponse(
                {
                    "success": True,
                    "message": message,
                    "sub_section_slug": self.sub_section.slug,
                    "sub_section_html": html,
                }
            )
        return super().form_valid(form)

    def form_invalid(self, form):
        if self.is_ajax():
            html = render_to_string(
                "dat/dat_sub_section_form.html",
                self.get_context_data(form=form, form_action=self.request.path),
                request=self.request,
            )
            return JsonResponse({"success": False, "form_html": html}, status=400)
        return super().form_invalid(form)

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        if self.is_ajax():
            html = render_to_string(
                "dat/dat_sub_section_form.html",
                self.get_context_data(form=response.context_data["form"], form_action=request.path),
                request=request,
            )
            return JsonResponse({"form_html": html, "title": self.sub_section.title})
        return response

    def get_success_url(self):
        anchor = f"#sub-section-{self.sub_section.slug}"
        return f"{reverse('dat:my_detail', args=[self.section.dat_id])}{anchor}"


class DatManagerAccessMixin(LoginRequiredMixin):
    """Ensure only management users can reach admin utilities."""

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not (user.is_authenticated and user_can_manage_dat(user)):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class DatAdminList(ModuleContextMixin, DatManagerAccessMixin, ListView):
    model = DAT
    template_name = "dat/dat_admin_list.html"
    context_object_name = "object_list"
    paginate_by = None

    def get_queryset(self):
        return DAT.objects.select_related("application", "owner").order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_dats"] = context["object_list"].count()
        return context


class DatImportView(ModuleContextMixin, DatManagerAccessMixin, FormView):
    template_name = "dat/dat_import.html"
    form_class = DATImportForm
    success_url = reverse_lazy("dat:import")

    def _deduplicate_messages(self):
        """
        Ensure the outgoing response only carries unique messages to avoid
        repeated toasts when the storage unexpectedly accumulates duplicates.
        """
        storage = messages.get_messages(self.request)
        unique = []
        seen = set()

        for msg in storage:
            key = (msg.level, msg.message, msg.extra_tags)
            if key in seen:
                continue
            seen.add(key)
            unique.append(msg)

        for msg in unique:
            messages.add_message(self.request, msg.level, msg.message, extra_tags=msg.extra_tags)

    def form_valid(self, form):
        importer = DATImportService(actor=self.request.user if self.request.user.is_authenticated else None)
        payload = form.payload or {}
        reference_override = form.cleaned_data.get("reference_override") or None
        try:
            result = importer.import_from_payload(payload, reference_override=reference_override)
        except DATImportError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        dat = result.dat
        messages.success(
            self.request,
            f"Le DAT « {dat.reference} - {dat.title} » a été importé avec succès.",
        )
        detail_url = reverse("dat:my_detail", args=[dat.pk])
        messages.info(
            self.request,
            format_html('Consulter le <a href="{}">DAT importé</a>.', detail_url),
        )
        for warning in result.warnings:
            messages.warning(self.request, warning)
        self._deduplicate_messages()
        return super().form_valid(form)


class DatDashboardView(ModuleContextMixin, DatManagerAccessMixin, TemplateView):
    template_name = "dat/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        total = DAT.objects.count()
        status_counts = DAT.objects.values("status").annotate(count=Count("id"))
        status_labels = dict(DATStatus.choices)
        status_order = {choice[0]: index for index, choice in enumerate(DATStatus.choices)}
        status_summary = {
            key: {
                "status": key,
                "label": label,
                "count": 0,
                "percentage": 0,
            }
            for key, label in status_labels.items()
        }
        for entry in status_counts:
            status = entry["status"]
            count = entry["count"]
            bucket = status_summary.get(status)
            if bucket:
                bucket["count"] = count
        if total:
            for bucket in status_summary.values():
                bucket["percentage"] = round(bucket["count"] / total * 100, 1)
        status_summary = sorted(status_summary.values(), key=lambda item: status_order.get(item["status"], len(status_order)))

        now = timezone.now()
        months = OrderedDict()
        base_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        def shift_month(start, delta):
            year = start.year + (start.month - 1 + delta) // 12
            month = (start.month - 1 + delta) % 12 + 1
            return start.replace(year=year, month=month, day=1)

        for offset in range(-5, 1):
            month_start = shift_month(base_month, offset)
            key = month_start.strftime("%Y-%m")
            label = month_start.strftime("%m/%Y")
            months[key] = {"label": label, "count": 0, "date": month_start}

        month_stats = (
            DAT.objects.filter(created_at__gte=list(months.values())[0]["date"])
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        for stat in month_stats:
            month = stat["month"]
            if month is None:
                continue
            key = month.strftime("%Y-%m")
            if key in months:
                months[key]["count"] = stat["count"]

        monthly_data = list(months.values())
        max_count = max((item["count"] for item in monthly_data), default=0)
        max_count = max_count or 1
        if len(monthly_data) > 1:
            step = 100 / (len(monthly_data) - 1)
        else:
            step = 100
        points = []
        for index, item in enumerate(monthly_data):
            x = index * step
            y = 100 - (item["count"] / max_count * 90) - 5  # keep within viewbox
            points.append(f"{x:.2f},{y:.2f}")
        line_points = " ".join(points)
        if line_points:
            area_points = f"0,100 {line_points} 100,100"
        else:
            area_points = "0,100 100,100"

        top_owners = (
            DAT.objects.values("owner__username")
            .annotate(total=Count("id"))
            .exclude(owner__username__isnull=True)
            .order_by("-total")[:5]
        )

        context.update(
            {
                "total_dats": total,
                "status_summary": status_summary,
                "monthly_activity": monthly_data,
                "monthly_chart_points": line_points,
                "monthly_chart_area_points": area_points,
                "top_owners": top_owners,
            }
        )

        return context


@login_required
def application_options(request):
    if not (user_can_manage_dat(request.user) or user_can_create_dat_entities(request.user)):
        raise PermissionDenied
    applications = (
        Application.objects.filter(business_direction__isnull=False)
        .order_by("name")
        .values("id", "name")
    )
    options = [
        {"value": application["id"], "label": application["name"]}
        for application in applications
    ]
    return JsonResponse({"options": options})


@login_required
def create_schema_diagram(request, dat_pk: int):
    if request.method != "POST":
        return JsonResponse({"error": "Méthode non autorisée"}, status=405)

    dat = get_object_or_404(DAT.objects.prefetch_related("sections__allowed_roles"), pk=dat_pk)
    architecture_section = dat.sections.filter(metadata__slug="architecture").first()
    if architecture_section is None:
        sync_dat_sections_if_needed(dat)
        architecture_section = dat.sections.filter(metadata__slug="architecture").first()
    if architecture_section is None or not architecture_section.can_user_edit(request.user):
        raise PermissionDenied

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}
    raw_title = (payload.get("title") or "").strip()
    if raw_title:
        try:
            title = sanitize_diagram_title(raw_title)
        except ValidationError as exc:
            message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            return JsonResponse(
                {"ok": False, "error": "invalid_title", "message": message},
                status=400,
            )
    else:
        fallback_title = f"{dat.reference} - Schéma"
        try:
            title = sanitize_diagram_title(fallback_title)
        except ValidationError:
            title = sanitize_diagram_title("Diagramme")

    diagram = DrawIODiagram.objects.create(title=title, owner=request.user)
    response_payload = {
        "ok": True,
        "diagram": {
            "id": diagram.pk,
            "title": diagram.title,
            "detail_url": reverse("diagrams:detail", args=[diagram.pk]),
            "edit_url": reverse("diagrams:edit", args=[diagram.pk]),
        },
    }
    return JsonResponse(response_payload, status=201)


def _normalize_diagram_ids(raw_ids) -> list[int]:
    if not isinstance(raw_ids, (list, tuple)):
        return []
    cleaned: list[int] = []
    seen = set()
    for raw in raw_ids:
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            continue
        if value < 1 or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned


LIKEC4_PROTOCOLS = {
    "amqp",
    "ftp",
    "grpc",
    "http",
    "https",
    "imap",
    "jdbc",
    "ldap",
    "ldaps",
    "mqtt",
    "nfs",
    "odbc",
    "pop3",
    "sftp",
    "smb",
    "smtp",
    "ssh",
    "tcp",
    "udp",
}


def _normalize_likec4_path(raw_path) -> str:
    if not raw_path:
        return ""
    cleaned = str(raw_path).strip().lstrip("/")
    if not cleaned or not cleaned.lower().endswith(".c4"):
        return ""
    parts = Path(cleaned).parts
    if any(part in (".", "..") for part in parts):
        return ""
    return cleaned


def _normalize_likec4_paths(raw_paths) -> list[str]:
    if not isinstance(raw_paths, (list, tuple)):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in raw_paths:
        normalized = _normalize_likec4_path(raw)
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def _extract_schema_likec4_paths(sub_section: DATSubSection) -> list[str]:
    if sub_section is None:
        return []
    part = sub_section.parts.filter(key="schemas").first()
    if part is None:
        return []
    rows = part.value or []
    if not isinstance(rows, list):
        return []
    paths = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tool = (row.get("schema_systeme") or "").strip().lower()
        if tool != "likec4":
            continue
        paths.append(row.get("schema_reference"))
    return _normalize_likec4_paths(paths)


def _guess_likec4_protocol(label: str) -> tuple[str, str]:
    if not label:
        return "", ""
    cleaned = re.sub(r"\s+", " ", str(label).strip())
    if not cleaned:
        return "", ""
    tokens = [token for token in re.split(r"[\s/,:;()\[\]-]+", cleaned) if token]
    protocol = ""
    port = ""
    for idx, token in enumerate(tokens):
        lower = token.lower()
        if lower in LIKEC4_PROTOCOLS:
            protocol = lower
            if idx + 1 < len(tokens) and str(tokens[idx + 1]).isdigit():
                port = str(tokens[idx + 1])
            break
    return protocol, port


def _fetch_likec4_flow_matrix(storage_path: str) -> dict | None:
    if not storage_path:
        return None
    base_url = getattr(settings, "LIKEC4_EDITOR_URL", "").strip()
    if not base_url:
        return None
    if not is_http_url(base_url):
        logger.warning("LikeC4 flow-matrix blocked: LIKEC4_EDITOR_URL must be http(s).")
        return None
    try:
        query = urlencode({"file": storage_path})
    except Exception:
        query = ""
    url = f"{base_url.rstrip('/')}/flow-matrix"
    if query:
        url = f"{url}?{query}"
    headers = {}
    api_token = getattr(settings, "LIKEC4_API_TOKEN", "").strip()
    if api_token:
        headers["X-LikeC4-Token"] = api_token
    try:
        request = Request(url, headers=headers)
        with urlopen(request, timeout=10) as response:
            status = getattr(response, "status", 200)
            if status < 200 or status >= 300:
                logger.warning("LikeC4 flow-matrix failed for %s: status=%s", storage_path, status)
                return None
            payload = json.loads(response.read().decode("utf-8", errors="ignore") or "{}")
            return payload if isinstance(payload, dict) else None
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        logger.warning(
            "LikeC4 flow-matrix failed for %s: status=%s body=%s",
            storage_path,
            exc.code,
            body[:200],
        )
        return None
    except Exception as exc:  # pragma: no cover - best effort parsing
        logger.warning("LikeC4 flow-matrix failed for %s: %s", storage_path, exc)
        return None


def _likec4_rows_from_flow_matrix(payload: dict) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if not isinstance(payload, dict):
        return [], []
    flows_raw = payload.get("flows")
    components_raw = payload.get("components")
    flows = flows_raw if isinstance(flows_raw, list) else []
    components = components_raw if isinstance(components_raw, list) else []

    briques: list[dict[str, str]] = []
    fluxes: list[dict[str, str]] = []
    component_titles: dict[str, str] = {}
    component_names: set[str] = set()

    for component in components:
        if not isinstance(component, dict):
            continue
        name = str(component.get("name") or "").strip()
        title = str(component.get("title") or "").strip()
        if not name and not title:
            continue
        display = title or name
        if name:
            component_titles[name] = display
            component_names.add(name.lower())
        row = {key: "" for key in BRIQUE_COLUMNS}
        row["brique_id"] = name or display
        row["nom"] = display
        props = component.get("props") if isinstance(component.get("props"), dict) else {}
        metadata = component.get("metadata") if isinstance(component.get("metadata"), dict) else {}
        description = ""
        for key in ("description", "commentaire", "details", "notes", "note"):
            description = (props.get(key) or metadata.get(key) or "").strip()
            if description:
                break
        row["description"] = description
        briques.append(row)

    def ensure_component_row(raw_name: str) -> None:
        name = str(raw_name or "").strip()
        if not name or name.lower() in component_names:
            return
        component_names.add(name.lower())
        row = {key: "" for key in BRIQUE_COLUMNS}
        row["brique_id"] = name
        row["nom"] = name
        row["description"] = ""
        briques.append(row)

    for flow in flows:
        if not isinstance(flow, dict):
            continue
        source_raw = str(flow.get("from") or "").strip()
        target_raw = str(flow.get("to") or "").strip()
        if not source_raw or not target_raw:
            continue
        label = str(flow.get("label") or "").strip()
        protocol, port = _guess_likec4_protocol(label)
        row = {key: "" for key in FLUX_COLUMNS}
        row["source"] = component_titles.get(source_raw, source_raw)
        row["cible"] = component_titles.get(target_raw, target_raw)
        if label:
            if protocol:
                row["protocole"] = protocol
                if port:
                    row["port"] = port
                if label.lower() != protocol:
                    row["flux_id"] = label
            else:
                row["flux_id"] = label
        if protocol == "https":
            row["chiffrement"] = "oui"
        elif protocol == "http":
            row["chiffrement"] = "non"
        fluxes.append(row)
        ensure_component_row(source_raw)
        ensure_component_row(target_raw)

    return briques, fluxes


def _extract_schema_diagram_ids(sub_section: DATSubSection) -> list[int]:
    if sub_section is None:
        return []
    part = sub_section.parts.filter(key="schemas").first()
    if part is None:
        return []
    rows = part.value or []
    if not isinstance(rows, list):
        return []
    ids = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ids.append(row.get("diagramme_id"))
    return _normalize_diagram_ids(ids)


def _update_repeater_part(part: DATPart, rows: list[dict[str, str]]) -> tuple[bool, dict[str, dict[str, str]]]:
    if part is None:
        return False, {}
    prepared = part.prepare_value(rows)
    if prepared == part.value:
        return False, {}
    before_display = part.render_value(part.value)
    part.update_value(prepared)
    after_display = part.render_value(part.value)
    if part.data_type == DATPartEntryType.REPEATER:
        before_display = json.dumps(before_display or [], ensure_ascii=False)
        after_display = json.dumps(after_display or [], ensure_ascii=False)
    return True, {
        part.key: {
            "label": part.label,
            "part": part.sub_section.title,
            "from": before_display,
            "to": after_display,
        }
    }


@login_required
@require_POST
def parse_schema_diagram(request, dat_pk: int):
    base_queryset = filter_dat_queryset_for_user(DAT.objects.all(), request.user)
    dat = get_object_or_404(base_queryset, pk=dat_pk)
    if dat.status in FINAL_DAT_STATUSES:
        raise PermissionDenied
    architecture_section = dat.sections.select_related("metadata").filter(metadata__slug="architecture").first()
    if architecture_section is None:
        sync_dat_sections_if_needed(dat)
        architecture_section = dat.sections.select_related("metadata").filter(metadata__slug="architecture").first()
    if architecture_section is None or not architecture_section.can_user_edit(request.user):
        raise PermissionDenied
    schema_sub_section = architecture_section.sub_sections.filter(slug="schemas").first()
    if schema_sub_section is None or not schema_sub_section.can_user_edit(request.user):
        raise PermissionDenied

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}

    diagram_ids = _normalize_diagram_ids(payload.get("diagram_ids"))
    likec4_paths = _normalize_likec4_paths(payload.get("likec4_paths"))
    if not diagram_ids and not likec4_paths:
        diagram_ids = _extract_schema_diagram_ids(schema_sub_section)
        likec4_paths = _extract_schema_likec4_paths(schema_sub_section)
    if not diagram_ids and not likec4_paths:
        return JsonResponse(
            {"ok": False, "error": "missing_diagrams", "message": "Aucun diagramme à analyser."},
            status=400,
        )

    diagrams = []
    if diagram_ids:
        diagrams = list(DrawIODiagram.objects.filter(pk__in=diagram_ids).only("pk", "xml_file"))
    if diagram_ids and not diagrams and not likec4_paths:
        return JsonResponse(
            {"ok": False, "error": "diagram_not_found", "message": "Aucun diagramme n'a été trouvé."},
            status=404,
        )

    briques_rows: list[dict[str, str]] = []
    flux_rows: list[dict[str, str]] = []
    if diagrams:
        for diagram in diagrams:
            diagram_xml = diagram.read_xml() or ""
            briques, fluxes = parse_architecture_diagram(diagram_xml)
            if briques:
                briques_rows.extend(briques)
            if fluxes:
                flux_rows.extend(fluxes)
    if likec4_paths:
        for path in likec4_paths:
            likec4_payload = _fetch_likec4_flow_matrix(path)
            if not likec4_payload:
                continue
            briques, fluxes = _likec4_rows_from_flow_matrix(likec4_payload)
            if briques:
                briques_rows.extend(briques)
            if fluxes:
                flux_rows.extend(fluxes)
    briques_rows, flux_rows = dedupe_architecture_rows(briques_rows, flux_rows)

    briques_sub_section = architecture_section.sub_sections.filter(slug="briques-techniques").first()
    flux_sub_section = architecture_section.sub_sections.filter(slug="flux").first()
    if briques_sub_section is None or flux_sub_section is None:
        return JsonResponse(
            {"ok": False, "error": "missing_sections", "message": "Sous-section introuvable."},
            status=400,
        )
    if not briques_sub_section.can_user_edit(request.user) or not flux_sub_section.can_user_edit(request.user):
        raise PermissionDenied

    briques_part = briques_sub_section.parts.filter(key="briques").first()
    flux_part = flux_sub_section.parts.filter(key="flux").first()
    if briques_part is None or flux_part is None:
        return JsonResponse(
            {"ok": False, "error": "missing_parts", "message": "Configuration du tableau introuvable."},
            status=400,
        )

    changes_by_sub_section: dict[str, dict[str, dict[str, str]]] = {}
    updated_briques, briques_changes = _update_repeater_part(briques_part, briques_rows)
    updated_flux, flux_changes = _update_repeater_part(flux_part, flux_rows)
    if updated_briques:
        changes_by_sub_section[briques_sub_section.slug] = briques_changes
    if updated_flux:
        changes_by_sub_section[flux_sub_section.slug] = flux_changes

    if changes_by_sub_section:
        actor_display = format_user_display(request.user)
        for sub_section_slug, changes in changes_by_sub_section.items():
            sub_section = briques_sub_section if sub_section_slug == briques_sub_section.slug else flux_sub_section
            DATHistory.objects.create(
                dat=dat,
                action=DATHistoryAction.SECTION_UPDATED,
                performed_by=request.user,
                performed_by_display=actor_display,
                details={
                    "section": {"slug": architecture_section.slug, "title": architecture_section.title},
                    "sub_section": {"slug": sub_section.slug, "title": sub_section.title},
                    "changes": changes,
                },
            )
        refresh_dat_status(dat, actor=request.user, force_in_progress=True)

    sub_sections_html: dict[str, str] = {}
    if updated_briques:
        sub_sections_html[briques_sub_section.slug] = render_sub_section_snippet(
            dat, request.user, architecture_section.slug, briques_sub_section.slug
        )
    if updated_flux:
        sub_sections_html[flux_sub_section.slug] = render_sub_section_snippet(
            dat, request.user, architecture_section.slug, flux_sub_section.slug
        )

    total_flux = len(flux_rows)
    total_briques = len(briques_rows)
    if total_flux or total_briques:
        message = f"Analyse terminée : {total_flux} flux, {total_briques} brique(s) détectée(s)."
    else:
        message = "Analyse terminée : aucun flux ou brique détecté."

    return JsonResponse(
        {
            "ok": True,
            "message": message,
            "parsed": {"flux": total_flux, "briques": total_briques},
            "updated": {"flux": updated_flux, "briques": updated_briques},
            "sub_sections": sub_sections_html,
        }
    )

