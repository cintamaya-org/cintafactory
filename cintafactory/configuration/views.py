from types import SimpleNamespace

from django.apps import apps as django_apps
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.views.generic import TemplateView
from material.frontend.registry import modules as module_registry


class ModuleContextMixin:
    """Ensure Material templates can resolve the current module layout."""

    module_app_label = "configuration"
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


class SuperAdminRequiredMixin(LoginRequiredMixin):
    """Restrict access to authenticated users flagged as Django superusers."""

    def _is_super_admin(self, request):
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and getattr(user, "is_superuser", False))

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not self._is_super_admin(request):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class ConfigurationHomeView(SuperAdminRequiredMixin, ModuleContextMixin, TemplateView):
    template_name = "configuration/index.html"
