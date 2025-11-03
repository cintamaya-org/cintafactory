from material import Layout, Row, Fieldset
from material.frontend.views import ModelViewSet
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from .forms import UserForm
from .models import Role, User
from django.views.generic import ListView

User = get_user_model()

class BaseSecuredViewSet(LoginRequiredMixin, ModelViewSet):
    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated

    def _can_mutate(self, request):
        return (
            request.user.is_superuser
            or request.user.is_staff
            or (hasattr(request.user, "is_role") and request.user.is_role("comite-validation"))
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
    layout = Layout(Row("name", "slug"))

class UserViewSet(LoginRequiredMixin, ModelViewSet):
    model = User
    queryset = User.objects.all()
    paginate_by = None
    list_display = ("username", "email", "first_name", "last_name", "role", "is_active")
    list_display_links = ("username",)
    ordering = ("username",)
    search_fields = ("username", "email", "first_name", "last_name")
    # list_template_name = "users/user_list.html"
    form_class = UserForm
    layout = Layout(
        Fieldset("Compte", Row("username", "email")),
        Fieldset("Profil", Row("first_name", "last_name")),
        Fieldset("Securite", Row("password1", "password2")),
        Fieldset("Roles et droits", Row("role", "architect_referent", "is_active", "is_staff", "is_superuser")),
    )


class RoleList(LoginRequiredMixin, ListView):
    model = Role
    template_name = "users/role_list.html"
    context_object_name = "object_list"

class UserList(LoginRequiredMixin, ListView):
    model = User
    template_name = "users/user_list.html"
    context_object_name = "object_list"
