from collections import OrderedDict

from django.apps import apps as django_apps
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.views.generic import ListView, TemplateView

from material import Fieldset, Layout, Row
from material.frontend.registry import modules as module_registry
from material.frontend.views import ModelViewSet

from .models import DAT

class BaseSecuredViewSet(LoginRequiredMixin, ModelViewSet):
    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated

    def _can_mutate(self, request):
        return (
            request.user.is_superuser
            or request.user.is_staff
            or (hasattr(request.user, "is_role") and request.user.is_role("admin"))
        )

    def has_add_permission(self, request): return self._can_mutate(request)
    def has_change_permission(self, request, obj=None): return self._can_mutate(request)
    def has_delete_permission(self, request, obj=None): return self._can_mutate(request)


class DATViewSet(BaseSecuredViewSet):
    model = DAT
    queryset = DAT.objects.all()
    paginate_by = None

    list_display = ("reference", "title", "status", "owner", "created_at")
    list_display_links = ("reference",)
    ordering = ("-created_at",)
    search_fields = ("reference", "title", "description")

    form_fields = ["reference", "title", "description", "status", "owner"]
    layout = Layout(
        Fieldset("Identity", Row("reference", "title")),
        Fieldset("Content", Row("description")),
        Fieldset("Workflow", Row("status", "owner")),
    )


class DatList(LoginRequiredMixin, ListView):
    model = DAT
    template_name = "dat/dat_list.html"
    context_object_name = "object_list"

    def get_queryset(self):
        return DAT.objects.filter(owner=self.request.user)

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
        return context


class DatManagerAccessMixin(LoginRequiredMixin):
    """Ensure only management users can reach admin utilities."""

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not (
            user.is_authenticated
            and (
                user.is_superuser
                or user.is_staff
                or (hasattr(user, "is_role") and user.is_role("admin"))
            )
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class DatDashboardView(DatManagerAccessMixin, TemplateView):
    template_name = "dat/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        total = DAT.objects.count()
        status_counts = DAT.objects.values("status").annotate(count=Count("id"))
        status_labels = dict(DAT.STATUS_CHOICES)
        status_order = {choice[0]: index for index, choice in enumerate(DAT.STATUS_CHOICES)}
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
            label = month_start.strftime("%b %Y")
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
