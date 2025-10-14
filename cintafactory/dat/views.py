# dat/views.py
from material import Layout, Row, Fieldset
from material.frontend.views import ModelViewSet
from material.frontend.views.create import CreateModelView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from .models import DAT, DATStatus
from .forms import DATForm


class BaseSecuredViewSet(LoginRequiredMixin, ModelViewSet):
    """
    Base guardrails similar to your Users/Roles modules:
    - Authenticated users can view
    - Only privileged roles can mutate
    """
    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated

    def _can_mutate(self, request):
        return (
            request.user.is_superuser
            or request.user.is_staff
            or (hasattr(request.user, "is_role") and request.user.is_role("admin"))
            or getattr(getattr(request.user, "role", None), "slug", None) == "admin"
        )

    def has_add_permission(self, request):
        return self._can_mutate(request)

    def has_change_permission(self, request, obj=None):
        return self._can_mutate(request)

    def has_delete_permission(self, request, obj=None):
        return self._can_mutate(request)


class DATCreateView(CreateModelView):
    """
    Material create view that injects request.user into the form and
    guarantees created_by/status are set before the object is saved.
    """
    form_class = DATForm  # ensure our form is used

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user  # let the form see the current user
        return kwargs

    def form_valid(self, form):
        # Safety net: enforce creator + Draft on POST before save
        form.instance.created_by = self.request.user
        form.instance.status = DATStatus.DRAFT
        return super().form_valid(form)


class DATViewSet(BaseSecuredViewSet):
    """
    Material CRUD for DAT.
    Routes (mounted via urls.py include):
      - Create: /dat/manage/dats/crud/add/
      - Change: /dat/manage/dats/crud/<pk>/change/
      - List:   /dat/manage/dats/crud/
    """
    model = DAT
    queryset = DAT.objects.all()
    paginate_by = None

    list_display = ("business_id", "title", "project_name", "status", "created_by", "created_at")
    list_display_links = ("business_id",)
    ordering = ("-created_at",)
    search_fields = ("business_id", "title", "project_name", "created_by__username")

    # Ensure the POST path uses our create view subclass
    create_view_class = DATCreateView

    # Keep form consistent across add/change and minimal fields
    form_class = DATForm
    add_form_class = DATForm
    change_form_class = DATForm
    form_fields = ["title", "project_name"]

    layout = Layout(
        Fieldset("General", Row("title", "project_name")),
        # Status is enforced to Draft on create; expose later if needed.
    )


class MyDATList(LoginRequiredMixin, ListView):
    """
    Material list page for the current user's DATs (My DAT).
    Template: templates/dat/dat_list.html
    URL:      /dat/my/
    """
    model = DAT
    template_name = "dat/dat_list.html"
    context_object_name = "object_list"

    def get_queryset(self):
        return DAT.objects.filter(created_by=self.request.user).order_by("-created_at")
