import json
import logging
from collections import OrderedDict
from types import SimpleNamespace
from urllib.parse import urlencode

from django.apps import apps as django_apps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Prefetch
from django.db.models.functions import TruncMonth
from django.http import FileResponse, HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.text import slugify
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView, FormView

from material import Fieldset, Layout, Row
from material.frontend.registry import modules as module_registry
from material.frontend.views import CreateModelView, DetailModelView, ListModelView, ModelViewSet, UpdateModelView

from diagrams.models import Diagram
from diagrams.validation import sanitize_diagram_title

from .constants import (
    DAT_PORTEUR_ROLE_SLUG,
    DAT_REQUIRED_PARTICIPANT_ROLE_LABELS,
    DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS,
    DAT_STATUS_REQUIRED_ROLES,
)
from .exporters import get_dat_export_model_builder
from .forms import DATForm, DATImportForm, DATSubSectionForm
from .importers import DATImportError, DATImportService
from .models import (
    Application,
    DAT,
    DATPart,
    DATPartEntry,
    DATSection,
    DATSubSection,
    DATStatus,
    DATHistory,
    DATHistoryAction,
)
from .pdf import generate_dat_pdf
from .permissions import filter_dat_queryset_for_user, user_is_dat_admin
from .sections import sync_dat_sections_if_needed
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


logger = logging.getLogger(__name__)

PORTEUR_ROLE_SLUG = DAT_PORTEUR_ROLE_SLUG
OWNER_EDITABLE_STATUSES = {
    DATStatus.DEMANDE_INITIALE,
    DATStatus.INSTRUCTION_ARCHITECTURE,
}
PROGRESSABLE_STATUSES = set(DAT_STATUS_REQUIRED_ROLES.keys())
STATUS_SEQUENCE = [choice.value for choice in DATStatus]
HISTORY_ENTRIES_PREFETCH = Prefetch(
    "history_entries",
    queryset=DATHistory.objects.select_related("performed_by").order_by("-performed_at", "-id"),
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


def get_required_roles_for_status(status: str) -> tuple[str, ...]:
    return DAT_STATUS_REQUIRED_ROLES.get(status, ())


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
    }


def build_section_payload(dat: DAT, user, section_slug: str | None = None, sub_section_slug: str | None = None):
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
    sections_qs = dat.sections.order_by("order", "id").prefetch_related(sub_section_prefetch)
    if section_slug:
        sections_qs = sections_qs.filter(slug=section_slug)
    sections_list = list(sections_qs)
    if section_slug and not sections_list:
        return []
    for section in sections_list:
        parts_payload = []
        for sub_section in section.sub_sections.all():
            if sub_section_slug and sub_section.slug != sub_section_slug:
                continue
            entries = list(sub_section.parts.all())
            parts_payload.append(
                {
                    "section_part": sub_section,
                    "entries": entries,
                    "can_edit": sub_section.can_user_edit(user),
                }
            )
        if sub_section_slug and not parts_payload:
            continue
        sections_payload.append(
            {
                "section": section,
                "parts": parts_payload,
                "can_edit": section.can_user_edit(user),
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
    try:
        index = STATUS_SEQUENCE.index(current_status)
    except ValueError:
        return None
    next_index = index + 1
    if next_index < len(STATUS_SEQUENCE):
        return STATUS_SEQUENCE[next_index]
    return None


def user_can_progress_dat(dat: DAT, user) -> bool:
    if dat is None or user is None or not getattr(user, "is_authenticated", False):
        return False
    if user_is_dat_admin(user):
        return True
    required_roles = get_required_roles_for_status(dat.status)
    if not required_roles:
        return False
    if dat.status not in PROGRESSABLE_STATUSES:
        return False
    next_status = get_next_status(dat.status)
    if not next_status:
        return False

    user_id = getattr(user, "id", None)
    for participant in dat.participants.all():
        role = getattr(participant, "role", None)
        if role is None:
            continue
        if participant.user_id == user_id and role.slug in required_roles:
            return True

    if (
        DAT_PORTEUR_ROLE_SLUG in required_roles
        and dat.owner_id == user_id
        and user_is_porteur_demande(user)
    ):
        return True

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


class DATDetailView(ModuleContextMixin, DetailModelView):
    template_name = "dat/dat_detail.html"

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
                "participants__role",
                "participants__user",
            )
        )
        return filter_dat_queryset_for_user(base_queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["history_entries"] = get_dat_history_entries(self.object)
        context["history_actions"] = DATHistoryAction
        context["participant_overview"] = build_participant_overview(self.object)
        context["current_responsibles"] = get_current_responsibles(self.object)
        context["sections_payload"] = build_section_payload(self.object, self.request.user)
        context["section_nav"] = list(
            self.object.sections.order_by("order", "id").values("slug", "title")
        )
        return context


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

    owner_editable_statuses = OWNER_EDITABLE_STATUSES

    def get_queryset(self):
        base_queryset = (
            DAT.objects.select_related("application", "application__business_direction", "business_direction", "owner")
            .order_by("-created_at")
        )
        return filter_dat_queryset_for_user(base_queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["owner_editable_statuses"] = {status.value for status in self.owner_editable_statuses}
        user = self.request.user
        context["owner_can_edit"] = user_is_dat_admin(user)
        context["can_create_dat"] = user_can_create_dat_entities(user)
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
                "participants__role",
                "participants__user",
            )
        )
        return filter_dat_queryset_for_user(base_queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["history_entries"] = get_dat_history_entries(self.object)
        context["history_actions"] = DATHistoryAction
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
        context.update(build_dat_overview_context(self.object, self.request.user))
        section_nav = [{"slug": "overview", "title": "DETAILS DU DAT"}]
        section_nav.extend(
            list(
                self.object.sections.order_by("order", "id").values("slug", "title")
            )
        )
        valid_slugs = {entry["slug"] for entry in section_nav}
        selected_slug = self.request.GET.get("section") or "overview"
        if selected_slug not in valid_slugs:
            selected_slug = "overview"
        context["section_nav"] = section_nav
        context["selected_section_slug"] = selected_slug
        if selected_slug == "overview":
            context["selected_sections"] = []
        else:
            context["selected_sections"] = build_section_payload(self.object, self.request.user, section_slug=selected_slug)
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
        base_queryset = DATSubSection.objects.select_related("section__dat").prefetch_related("allowed_roles")
        self.sub_section = get_object_or_404(
            base_queryset,
            section__dat_id=dat_pk,
            section__slug=section_slug,
            slug=sub_section_slug,
        )
        self.section = self.sub_section.section
        if sync_dat_sections_if_needed(self.section.dat):
            self.sub_section = get_object_or_404(
                base_queryset,
                section__dat_id=dat_pk,
                section__slug=section_slug,
                slug=sub_section_slug,
            )
            self.section = self.sub_section.section
        if not self.sub_section.can_user_edit(request.user):
            raise PermissionDenied
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
                status_before=dat.status,
                status_after=dat.status,
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

    def form_valid(self, form):
        importer = DATImportService(actor=self.request.user if self.request.user.is_authenticated else None)
        payload = form.payload or {}
        try:
            result = importer.import_from_payload(payload)
        except DATImportError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        dat = result.dat
        messages.success(
            self.request,
            f"Le DAT « {dat.reference} - {dat.title} » a été importé avec succès.",
        )
        detail_url = f"/dat/manage/dats/crud/{dat.pk}/detail/"
        messages.info(
            self.request,
            format_html('Consulter le <a href="{}">DAT importé</a>.', detail_url),
        )
        for warning in result.warnings:
            messages.warning(self.request, warning)
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
    applications = Application.objects.order_by("name").values("id", "name")
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
    architecture_section = dat.sections.filter(slug="architecture").first()
    if architecture_section is None:
        sync_dat_sections_if_needed(dat)
        architecture_section = dat.sections.filter(slug="architecture").first()
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

    diagram = Diagram.objects.create(title=title, owner=request.user)
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


class DatAdvanceStatusView(LoginRequiredMixin, View):
    def post(self, request, pk: int, *args, **kwargs):
        queryset = filter_dat_queryset_for_user(
            DAT.objects.select_related("application", "owner"),
            request.user,
        )
        dat = get_object_or_404(queryset, pk=pk)

        if not user_can_progress_dat(dat, request.user):
            raise PermissionDenied

        next_status = get_next_status(dat.status)
        if not next_status:
            raise PermissionDenied

        dat.status = next_status
        dat._history_actor = request.user  # type: ignore[attr-defined]
        dat.save(update_fields=["status", "updated_at"])

        return redirect(reverse("dat:my_detail", args=[dat.pk]))
