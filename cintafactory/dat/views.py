from collections import OrderedDict

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from material import Fieldset, Layout, Row
from material.frontend.registry import modules as module_registry
from material.frontend.views import CreateModelView, DetailModelView, ModelViewSet, UpdateModelView

from .forms import DATForm
from .models import Application, DAT, DATStatus
from .permissions import filter_dat_queryset_for_user, user_is_dat_admin


PORTEUR_ROLE_SLUG = "porteur-demande"
OWNER_EDITABLE_STATUSES = {
    DATStatus.DEMANDE_INITIALE,
    DATStatus.INSTRUCTION_ARCHITECTURE,
}
PROGRESSABLE_STATUSES = OWNER_EDITABLE_STATUSES
STATUS_SEQUENCE = [choice.value for choice in DATStatus]


def user_is_porteur_demande(user):
    return bool(getattr(user, "is_role", None) and user.is_role(PORTEUR_ROLE_SLUG))


def user_can_create_dat_entities(user):
    return bool(user.is_authenticated and user_is_porteur_demande(user))


def user_can_manage_dat(user):
    return (
        user.is_superuser
        or user.is_staff
        or (hasattr(user, "is_role") and user.is_role("admin"))
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
    if dat.owner_id != getattr(user, "id", None):
        return False
    if not user_is_porteur_demande(user):
        return False
    if dat.status not in PROGRESSABLE_STATUSES:
        return False
    return get_next_status(dat.status) is not None


class BaseSecuredViewSet(LoginRequiredMixin, ModelViewSet):
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


class DATCreateView(CreateModelView):
    def dispatch(self, request, *args, **kwargs):
        if not user_can_create_dat_entities(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class DATUpdateView(UpdateModelView):
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class DATDetailView(DetailModelView):
    template_name = "dat/dat_detail.html"

    def get_queryset(self):
        base_queryset = DAT.objects.select_related("application", "owner")
        return filter_dat_queryset_for_user(base_queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        history_qs = (
            self.object.history_entries.select_related("performed_by")
            .order_by("-performed_at", "-id")
        )
        context["history_entries"] = list(history_qs)
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

    list_display = ("reference", "title", "application", "status", "owner", "created_at")
    list_display_links = ("reference",)
    ordering = ("-created_at",)
    search_fields = ("reference", "title", "description", "application__name", "application__code")

    layout = Layout(
        Fieldset("Identite", Row("reference", "title"), Row("application")),
        Fieldset("Contenu", Row("description")),
        Fieldset("Flux", Row("status", "owner")),
    )

    def get_queryset(self, request):
        base_queryset = (
            DAT.objects.select_related("application", "owner")
            .order_by("-created_at")
        )
        return filter_dat_queryset_for_user(base_queryset, request.user)


class ApplicationCreateView(CreateModelView):
    def dispatch(self, request, *args, **kwargs):
        if not user_can_create_dat_entities(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class ApplicationViewSet(BaseSecuredViewSet):
    model = Application
    queryset = Application.objects.all()
    paginate_by = None
    create_view_class = ApplicationCreateView

    def _can_add(self, request):
        return user_can_create_dat_entities(request.user)

    list_display = ("code", "name", "formatted_created_at", "formatted_updated_at")
    list_display_links = ("code",)
    ordering = ("name",)
    search_fields = ("code", "name", "description")

    form_fields = ["code", "name", "description"]
    layout = Layout(
        Fieldset("Identite", Row("code", "name")),
        Fieldset("Description", Row("description")),
    )


class DatList(LoginRequiredMixin, ListView):
    model = DAT
    template_name = "dat/dat_list.html"
    context_object_name = "object_list"

    owner_editable_statuses = OWNER_EDITABLE_STATUSES

    def get_queryset(self):
        base_queryset = (
            DAT.objects.select_related("application", "owner")
            .order_by("-created_at")
        )
        return filter_dat_queryset_for_user(base_queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        module = None
        resolver_match = getattr(self.request, "resolver_match", None)
        if resolver_match:
            module_label = resolver_match.namespace or resolver_match.app_name
            if module_label:
                module = module_registry.get_module(module_label)
        if module is None:
            try:
                module = django_apps.get_app_config("dat")
            except LookupError:
                module = None
        if module:
            context.setdefault("current_module", module)
        context["owner_editable_statuses"] = {status.value for status in self.owner_editable_statuses}
        user = self.request.user
        context["owner_can_edit"] = user_is_dat_admin(user)
        context["can_create_dat"] = user_can_create_dat_entities(user)
        return context


class DatDetail(LoginRequiredMixin, DetailView):
    model = DAT
    template_name = "dat/my_dat_detail.html"
    context_object_name = "dat"

    def get_queryset(self):
        base_queryset = (
            DAT.objects.select_related("application", "owner")
            .prefetch_related("history_entries__performed_by")
        )
        return filter_dat_queryset_for_user(base_queryset, self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        module = None
        resolver_match = getattr(self.request, "resolver_match", None)
        if resolver_match:
            module_label = resolver_match.namespace or resolver_match.app_name
            if module_label:
                module = module_registry.get_module(module_label)
        if module is None:
            try:
                module = django_apps.get_app_config("dat")
            except LookupError:
                module = None
        if module:
            context.setdefault("current_module", module)
        history_qs = (
            self.object.history_entries.select_related("performed_by")
            .order_by("-performed_at", "-id")
        )
        context["history_entries"] = list(history_qs)
        context["owner_editable_statuses"] = {status.value for status in OWNER_EDITABLE_STATUSES}
        context["owner_can_edit"] = user_is_dat_admin(self.request.user)
        context["can_create_dat"] = user_can_create_dat_entities(self.request.user)
        next_status = get_next_status(self.object.status)
        context["next_status"] = next_status
        context["next_status_label"] = DATStatus(next_status).label if next_status else None
        context["can_progress_dat"] = user_can_progress_dat(self.object, self.request.user)
        return context


class DatManagerAccessMixin(LoginRequiredMixin):
    """Ensure only management users can reach admin utilities."""

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not (user.is_authenticated and user_can_manage_dat(user)):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class DatAdminList(DatManagerAccessMixin, ListView):
    model = DAT
    template_name = "dat/dat_admin_list.html"
    context_object_name = "object_list"
    paginate_by = None

    def get_queryset(self):
        return DAT.objects.select_related("application", "owner").order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        module = None
        resolver_match = getattr(self.request, "resolver_match", None)
        if resolver_match:
            module_label = resolver_match.namespace or resolver_match.app_name
            if module_label:
                module = module_registry.get_module(module_label)
        if module is None:
            try:
                module = django_apps.get_app_config("dat")
            except LookupError:
                module = None
        if module:
            context.setdefault("current_module", module)
        context["total_dats"] = context["object_list"].count()
        return context


class DatDashboardView(DatManagerAccessMixin, TemplateView):
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

        module = None
        resolver_match = getattr(self.request, "resolver_match", None)
        if resolver_match:
            module_label = resolver_match.namespace or resolver_match.app_name
            if module_label:
                module = module_registry.get_module(module_label)
        if module is None:
            try:
                module = django_apps.get_app_config("dat")
            except LookupError:
                module = None
        if module:
            context.setdefault("current_module", module)
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
