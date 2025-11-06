import base64
import json
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, TemplateView
from django.templatetags.static import static
from PIL import Image
from material.frontend.registry import modules as module_registry
from types import SimpleNamespace

from .forms import DiagramForm
from .models import Diagram


DRAWIO_DEFAULT_LIBS = "general"


class ModuleContextMixin:
    """Ensure Material templates always have a base layout to extend."""

    module_app_label = "diagrams"
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


class DiagramListView(ModuleContextMixin, LoginRequiredMixin, ListView):
    template_name = "diagrams/list.html"
    context_object_name = "diagrams"

    def get_queryset(self):
        return Diagram.objects.filter(owner=self.request.user)


class DiagramCreateView(ModuleContextMixin, LoginRequiredMixin, CreateView):
    template_name = "diagrams/create.html"
    form_class = DiagramForm

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.owner = self.request.user
        obj.xml = "<mxGraphModel/>"
        obj.save()
        return redirect("diagrams:edit", pk=obj.pk)


class DiagramDetailView(ModuleContextMixin, LoginRequiredMixin, DetailView):
    template_name = "diagrams/detail.html"
    model = Diagram

    def get_queryset(self):
        return Diagram.objects.filter(owner=self.request.user)


class DiagramEditView(ModuleContextMixin, LoginRequiredMixin, TemplateView):
    template_name = "diagrams/edit.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        diagram = get_object_or_404(Diagram, pk=kwargs["pk"], owner=self.request.user)
        context["diagram"] = diagram
        library_urls = self._get_custom_library_urls()
        clibs_param = self._encode_custom_libraries(library_urls)
        context["drawio_embed_url"] = self._build_embed_url(clibs_param)
        context["drawio_origin"] = settings.DRAWIO_PUBLIC_ORIGIN
        return context

    def _get_custom_library_urls(self) -> list[str]:
        """Build absolute URLs for custom draw.io XML libraries."""
        candidate_dirs = [
            Path(settings.BASE_DIR) / "cintafactory" / "static" / "diagrams",
            Path(settings.BASE_DIR) / "static" / "diagrams",
        ]
        static_root = next((path for path in candidate_dirs if path.exists()), None)
        if static_root is None:
            return []
        libraries: list[str] = []
        request = self.request
        base_url = ""
        if request is None:
            base_url = settings.DRAWIO_LIBRARY_BASE_URL or settings.DRAWIO_PUBLIC_URL
        for entry in sorted(static_root.iterdir()):
            if not entry.is_file():
                continue
            if entry.name.endswith(":Zone.Identifier"):
                continue
            if entry.suffix.lower() != ".xml":
                continue
            relative_url = static(f"diagrams/{entry.name}")
            if request is not None:
                absolute_url = request.build_absolute_uri(relative_url)
            else:
                absolute_url = f"{base_url.rstrip('/')}/{relative_url.lstrip('/')}"
            libraries.append(absolute_url)
        return libraries

    def _encode_custom_libraries(self, urls: list[str]) -> str:
        if not urls:
            return ""
        encoded = ["U" + quote(url, safe="") for url in urls]
        return ";".join(encoded)

    def _build_embed_url(self, clibs_param: str) -> str:
        base_parts = urlsplit(settings.DRAWIO_PUBLIC_URL)
        base_path = base_parts.path or "/"
        base_query = base_parts.query
        query = (
            "embed=1&ui=min&spin=0&proto=json&lang=fr&autosave=1&tabs=0&libs="
            + DRAWIO_DEFAULT_LIBS
        )
        if clibs_param:
            query += f"&clibs={clibs_param}"
        if base_query:
            query = f"{base_query}&{query}"
        return urlunsplit(
            (
                base_parts.scheme or "https",
                base_parts.netloc,
                base_path,
                query,
                base_parts.fragment,
            )
        )


@login_required
@require_POST
def diagram_save_xml(request, pk: int):
    diagram = get_object_or_404(Diagram, pk=pk, owner=request.user)
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid payload"}, status=400)

    xml = data.get("xml", "")
    if not isinstance(xml, str):
        return JsonResponse({"ok": False, "error": "invalid xml"}, status=400)

    diagram.xml = xml
    diagram.updated_at = timezone.now()
    diagram.save(update_fields=["xml", "updated_at"])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def diagram_save_thumbnail(request, pk: int):
    diagram = get_object_or_404(Diagram, pk=pk, owner=request.user)
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid payload"}, status=400)

    data_uri = data.get("data_uri")
    if not (isinstance(data_uri, str) and data_uri.startswith("data:image/png;base64,")):
        return JsonResponse({"ok": False, "error": "expected PNG data URI"}, status=400)

    b64 = data_uri.split(",", 1)[1]
    raw = base64.b64decode(b64)

    image = Image.open(BytesIO(raw)).convert("RGBA")
    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)

    diagram.thumbnail.save("thumb.png", ContentFile(output.read()), save=False)
    diagram.updated_at = timezone.now()
    diagram.save(update_fields=["thumbnail", "updated_at"])

    return JsonResponse({"ok": True, "thumbnail_url": diagram.thumbnail.url})
