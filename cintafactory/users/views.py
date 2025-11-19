from material import Layout, Row, Fieldset
from material.frontend.views import CreateModelView, DetailModelView, ModelViewSet, UpdateModelView
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from material.frontend.registry import modules as module_registry
from types import SimpleNamespace
from django.db.models import Count

from .forms import BusinessDirectionForm, BusinessGroupForm, ProjectDirectionForm, UserForm
from .models import BusinessDirection, BusinessGroup, ProjectDirection, Role, User
from django.views.generic import ListView

User = get_user_model()


class ModuleContextMixin:
    """Ensure a usable `current_module` for Material templates."""

    module_app_label = "users"
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


class ModuleAwareCreateView(ModuleContextMixin, CreateModelView):
    pass


class ModuleAwareUpdateView(ModuleContextMixin, UpdateModelView):
    pass


class ModuleAwareDetailView(ModuleContextMixin, DetailModelView):
    pass


class BaseSecuredViewSet(LoginRequiredMixin, ModelViewSet):
    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated

    def _can_mutate(self, request):
        user = getattr(request, "user", None)
        if user is None:
            return False
        is_role = getattr(user, "is_role", None)
        return (
            getattr(user, "is_superuser", False)
            or getattr(user, "is_staff", False)
            or (callable(is_role) and is_role("comite-validation"))
        )

    def has_add_permission(self, request): return self._can_mutate(request)
    def has_change_permission(self, request, obj=None): return self._can_mutate(request)
    def has_delete_permission(self, request, obj=None): return self._can_mutate(request)
    def get_list_context_data(self, **kwargs):
            context = super().get_list_context_data(**kwargs)
            # Always provide object_list as a queryset of model instances
            context["object_list"] = self.get_queryset()
            return context

class RoleViewSet(LoginRequiredMixin, ModelViewSet):
    model = Role
    queryset = Role.objects.all()
    paginate_by = None
    list_display = ("name", "slug")
    list_display_links = ("name",)
    ordering = ("name",)
    search_fields = ("name", "slug")
    # list_template_name = "users/role_list.html"
    create_view_class = ModuleAwareCreateView
    update_view_class = ModuleAwareUpdateView
    detail_view_class = ModuleAwareDetailView
    layout = Layout(Row("name", "slug"))


class ProjectDirectionViewSet(LoginRequiredMixin, ModelViewSet):
    model = ProjectDirection
    queryset = ProjectDirection.objects.all()
    paginate_by = None
    list_display = ("name", "slug")
    list_display_links = ("name",)
    ordering = ("name",)
    search_fields = ("name", "slug")
    form_class = ProjectDirectionForm
    create_view_class = ModuleAwareCreateView
    update_view_class = ModuleAwareUpdateView
    detail_view_class = ModuleAwareDetailView
    layout = Layout(Row("name", "slug"))


class BusinessDirectionViewSet(LoginRequiredMixin, ModelViewSet):
    model = BusinessDirection
    queryset = BusinessDirection.objects.all()
    paginate_by = None
    list_display = ("name", "slug")
    list_display_links = ("name",)
    ordering = ("name",)
    search_fields = ("name", "slug")
    form_class = BusinessDirectionForm
    create_view_class = ModuleAwareCreateView
    update_view_class = ModuleAwareUpdateView
    detail_view_class = ModuleAwareDetailView
    layout = Layout(Row("name", "slug"))


class BusinessGroupViewSet(LoginRequiredMixin, ModelViewSet):
    model = BusinessGroup
    queryset = BusinessGroup.objects.select_related("direction", "business_direction", "responsible").annotate(
        user_total=Count("users")
    )
    paginate_by = None
    list_display = ("name", "direction", "business_direction", "responsible", "is_default", "user_total")
    list_display_links = ("name",)
    ordering = ("name",)
    search_fields = ("name", "direction__name", "business_direction__name", "responsible__username")
    form_class = BusinessGroupForm
    create_view_class = ModuleAwareCreateView
    update_view_class = ModuleAwareUpdateView
    detail_view_class = ModuleAwareDetailView
    layout = Layout(
        Fieldset("Groupe", Row("name", "direction", "business_direction")),
        Fieldset("Responsable", Row("responsible")),
    )

    def user_total(self, obj):
        return obj.member_count

    user_total.short_description = "Utilisateurs"

    def get_list_context_data(self, **kwargs):
        context = super().get_list_context_data(**kwargs)
        context["object_list"] = self.get_queryset()
        return context


class UserViewSet(LoginRequiredMixin, ModelViewSet):
    model = User
    queryset = User.objects.select_related(
        "business_group",
        "business_group__direction",
        "business_group__business_direction",
        "business_group__responsible",
        "role",
    )
    paginate_by = None
    list_display = ("username", "email", "first_name", "last_name", "business_group", "business_direction", "role", "is_active")
    list_display_links = ("username",)
    ordering = ("username",)
    search_fields = ("username", "email", "first_name", "last_name")
    # list_template_name = "users/user_list.html"
    form_class = UserForm
    create_view_class = ModuleAwareCreateView
    update_view_class = ModuleAwareUpdateView
    detail_view_class = ModuleAwareDetailView
    layout = Layout(
        Fieldset("Compte", Row("username", "email")),
        Fieldset("Profil", Row("first_name", "last_name")),
        Fieldset("Organisation", Row("business_group", "role")),
        Fieldset("Securite", Row("password1", "password2")),
        Fieldset("Roles et droits", Row("is_active", "is_staff", "is_superuser")),
    )


class RoleList(LoginRequiredMixin, ListView):
    model = Role
    template_name = "users/role_list.html"
    context_object_name = "object_list"


class ProjectDirectionList(LoginRequiredMixin, ListView):
    model = ProjectDirection
    template_name = "users/project_direction_list.html"
    context_object_name = "object_list"


class BusinessDirectionList(LoginRequiredMixin, ListView):
    model = BusinessDirection
    template_name = "users/business_direction_list.html"
    context_object_name = "object_list"

class UserList(LoginRequiredMixin, ListView):
    model = User
    template_name = "users/user_list.html"
    context_object_name = "object_list"

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.select_related(
            "business_group",
            "business_group__direction",
            "business_group__business_direction",
            "business_group__responsible",
            "role",
        )

    def business_direction(self, obj):
        group = getattr(obj, "business_group", None)
        if group:
            return group.business_direction
        return None


class BusinessGroupList(LoginRequiredMixin, ListView):
    model = BusinessGroup
    template_name = "users/group_list.html"
    context_object_name = "object_list"

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.select_related("direction", "responsible").annotate(user_total=Count("users"))
