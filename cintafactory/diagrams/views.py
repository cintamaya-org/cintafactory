import base64
import hashlib
import json
import logging
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_POST, require_http_methods
from django.views.generic import CreateView, DetailView, ListView, TemplateView
from django.templatetags.static import static
from material.frontend.registry import modules as module_registry
from types import SimpleNamespace

from .forms import DiagramForm
from .models import Diagram
from .validation import validate_drawio_xml


DRAWIO_DEFAULT_LIBS = "general"
logger = logging.getLogger(__name__)


def _build_import_log_context(request, diagram, uploaded_file=None) -> dict:
    user = getattr(request, "user", None)
    username = None
    if user is not None:
        if hasattr(user, "get_username"):
            try:
                username = user.get_username()
            except Exception:
                username = getattr(user, "username", None)
        else:
            username = getattr(user, "username", None)
    context = {
        "diagram_id": getattr(diagram, "pk", None),
        "diagram_title": getattr(diagram, "title", None),
        "user_id": getattr(user, "id", None),
        "username": username,
    }
    if uploaded_file is not None:
        context.update(
            {
                "file_name": getattr(uploaded_file, "name", None),
                "file_size": getattr(uploaded_file, "size", None),
                "content_type": getattr(uploaded_file, "content_type", None),
            }
        )
    return context


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


def _discover_static_library_urls(request=None) -> list[str]:
    """Locate custom draw.io XML libraries shipped with the project."""
    candidate_dirs = [
        Path(settings.BASE_DIR) / "cintafactory" / "static" / "diagrams",
        Path(settings.BASE_DIR) / "static" / "diagrams",
    ]
    static_root = next((path for path in candidate_dirs if path.exists()), None)
    if static_root is None:
        return []
    urls: list[str] = []
    for entry in sorted(static_root.iterdir()):
        if not entry.is_file():
            continue
        if entry.name.endswith(":Zone.Identifier"):
            continue
        if entry.suffix.lower() != ".xml":
            continue
        relative_url = static(f"diagrams/{entry.name}")
        if request is not None:
            urls.append(request.build_absolute_uri(relative_url))
        else:
            base_url = settings.DRAWIO_PUBLIC_URL
            urls.append(f"{base_url.rstrip('/')}/{relative_url.lstrip('/')}")
    return urls


def _collect_library_urls(request=None) -> list[str]:
    configured = [url for url in settings.DRAWIO_CLIBS]
    discovered = _discover_static_library_urls(request)
    if configured:
        extras = [url for url in discovered if url not in configured]
        return configured + extras
    return discovered


def _origin_from(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return url


def _request_is_secure(request) -> bool:
    if request is None:
        return False
    forwarded_proto = request.META.get("HTTP_X_FORWARDED_PROTO", "")
    proto = forwarded_proto.split(",")[0].strip().lower() if forwarded_proto else ""
    return getattr(request, "is_secure", lambda: False)() or proto == "https"


def _proxy_public_url(request=None) -> str:
    base_path = reverse("diagrams:drawio_proxy_root")
    if not base_path.endswith("/"):
        base_path = base_path + "/"
    if request is None:
        return base_path
    return request.build_absolute_uri(base_path)


def _resolve_public_drawio_url(request=None) -> str:
    """
    Pick a browser-facing draw.io URL without requiring env updates.

    If the configured draw.io URL is HTTP but the incoming request is HTTPS,
    serve the editor through a local reverse-proxy endpoint to avoid mixed
    content. Otherwise, use the configured public URL as-is.
    """
    public_url = getattr(settings, "DRAWIO_PUBLIC_URL", "")
    try:
        parts = urlsplit(public_url)
    except Exception:
        parts = None
    if parts and parts.scheme == "http" and _request_is_secure(request):
        return _proxy_public_url(request)
    return public_url


def _build_embed_url(library_urls: list[str], public_url: str | None = None, request=None) -> str:
    base_url = public_url or settings.DRAWIO_PUBLIC_URL
    base_parts = urlsplit(base_url)
    if not base_parts.netloc and request is not None:
        # Ensure we generate an absolute URL when the proxy path is relative.
        base_url = request.build_absolute_uri(base_url)
        base_parts = urlsplit(base_url)
    base_path = base_parts.path or "/"
    base_query = base_parts.query
    libs = settings.DRAWIO_LIBS or DRAWIO_DEFAULT_LIBS
    params = {
        "embed": "1",
        "ui": "min",
        "spin": "0",
        "proto": "json",
        "lang": "fr",
        "autosave": "1",
        "tabs": "0",
        "libs": libs,
    }
    query = urlencode(params)
    if library_urls:
        encoded = ";".join(f"U{quote(url, safe='')}" for url in library_urls)
        query = f"{query}&clibs={encoded}"
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


def _current_thumbnail_url(diagram: Diagram) -> str | None:
    field = getattr(diagram, "thumbnail", None)
    if not field or not getattr(field, "name", None):
        return None
    try:
        storage = field.storage
    except Exception as exc:  # pragma: no cover - storage misconfiguration
        logger.warning("diagram %s: thumbnail storage unavailable: %s", diagram.pk, exc)
        return None
    try:
        exists = storage.exists(field.name)
    except Exception as exc:  # pragma: no cover - storage failure best-effort
        logger.warning("diagram %s: unable to check thumbnail existence: %s", diagram.pk, exc)
        return None
    if not exists:
        return None
    try:
        return field.url
    except Exception as exc:  # pragma: no cover - storage failure best-effort
        logger.warning("diagram %s: unable to build thumbnail URL: %s", diagram.pk, exc)
        return None


def _save_thumbnail_from_data_uri(diagram: Diagram, data_uri: str) -> bool:
    if not (isinstance(data_uri, str) and data_uri.startswith("data:image/png;base64,")):
        return False
    b64 = data_uri.split(",", 1)[1]
    try:
        raw = base64.b64decode(b64)
    except (ValueError, TypeError):
        return False
    new_hash = hashlib.sha256(raw).hexdigest()
    current_hash = None
    field = getattr(diagram, "thumbnail", None)
    if field and getattr(field, "name", None):
        try:
            field.open("rb")
            current_hash = hashlib.sha256(field.read()).hexdigest()
        except FileNotFoundError:
            current_hash = None
        except Exception:  # pragma: no cover - best effort
            logger.warning("diagram %s: unable to read existing thumbnail for diffing", diagram.pk)
            current_hash = None
        finally:
            try:
                field.close()
            except Exception:
                pass
    if current_hash and current_hash == new_hash:
        diagram.updated_at = timezone.now()
        diagram.save(update_fields=["updated_at"])
        return True
    diagram.thumbnail.save("thumb.png", ContentFile(raw), save=False)
    diagram.updated_at = timezone.now()
    diagram.save(update_fields=["thumbnail", "updated_at"])
    return True


def _generate_thumbnail_data_uri_from_drawio(xml_payload: str) -> str | None:
    candidates: list[str] = []
    configured_export = getattr(settings, "DRAWIO_EXPORT_URL", "").rstrip("/")
    if configured_export:
        candidates.append(configured_export)
    base_url = getattr(settings, "DRAWIO_BASE_URL", "").rstrip("/")
    fallback_export = f"{base_url}/export" if base_url else ""
    if fallback_export and fallback_export not in candidates:
        candidates.append(fallback_export)
    if not candidates:
        return None

    payload = urlencode(
        {
            "format": "png",
            "scale": "1",
            "xml": xml_payload or "<mxGraphModel/>",
            "bg": "#ffffff",
            "base64": "1",
        }
    ).encode("utf-8")

    for export_url in candidates:
        request = Request(export_url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlopen(request, timeout=30) as response:
                if response.status != 200:
                    raise ValueError(f"HTTP {response.status}")
                payload_base64 = response.read().decode("utf-8").strip()
        except Exception as exc:  # pragma: no cover - best-effort thumbnail generation
            logger.warning("Impossible de générer la miniature Draw.io via %s: %s", export_url, exc)
            continue
        if payload_base64:
            return "data:image/png;base64," + payload_base64
    return None


def _regenerate_drawio_thumbnail(diagram: Diagram, xml_payload: str) -> bool:
    data_uri = _generate_thumbnail_data_uri_from_drawio(xml_payload)
    if not data_uri:
        return False
    return _save_thumbnail_from_data_uri(diagram, data_uri)


class DiagramEditView(ModuleContextMixin, LoginRequiredMixin, TemplateView):
    template_name = "diagrams/edit.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        diagram = get_object_or_404(Diagram, pk=kwargs["pk"], owner=self.request.user)
        context["diagram"] = diagram
        library_urls = _collect_library_urls(self.request)
        public_url = _resolve_public_drawio_url(self.request)
        context["drawio_embed_url"] = _build_embed_url(library_urls, public_url, self.request)
        context["drawio_origin"] = _origin_from(public_url)
        return context


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
    if not _save_thumbnail_from_data_uri(diagram, data_uri):
        return JsonResponse({"ok": False, "error": "expected PNG data URI"}, status=400)
    return JsonResponse({"ok": True, "thumbnail_url": diagram.thumbnail.url})


@require_http_methods(["GET", "HEAD"])
@xframe_options_exempt
def drawio_proxy(request, path: str = ""):
    """
    Lightweight reverse proxy to expose the draw.io service over HTTPS.
    """
    upstream_base = settings.DRAWIO_BASE_URL.rstrip("/")
    upstream = upstream_base if not path else f"{upstream_base}/{path.lstrip('/')}"
    query = request.META.get("QUERY_STRING")
    if query:
        upstream = f"{upstream}?{query}"

    method = "HEAD" if request.method == "HEAD" else "GET"
    headers = {}
    user_agent = request.headers.get("User-Agent")
    if user_agent:
        headers["User-Agent"] = user_agent

    try:
        req = Request(upstream, headers=headers, method=method)
        with urlopen(req, timeout=20) as resp:
            status = getattr(resp, "status", 200)
            body = b"" if method == "HEAD" else resp.read()
            content_type = resp.headers.get("Content-Type") or "application/octet-stream"
            response = HttpResponse(body, status=status)
            response["Content-Type"] = content_type
            for header_name in ("Cache-Control", "ETag", "Last-Modified", "Expires"):
                header_val = resp.headers.get(header_name)
                if header_val:
                    response[header_name] = header_val
            return response
    except Exception as exc:  # pragma: no cover - network/runtime failures
        logger.warning("draw.io proxy failed for %s: %s", upstream, exc)
        raise Http404("draw.io unavailable")


@login_required
def diagram_embed_context(request, pk: int):
    diagram = get_object_or_404(Diagram, pk=pk, owner=request.user)
    library_urls = _collect_library_urls(request)
    public_url = _resolve_public_drawio_url(request)
    embed_url = _build_embed_url(library_urls, public_url, request)
    payload = {
        "ok": True,
        "diagram": {"id": diagram.pk, "title": diagram.title},
        "drawio": {
            "embed_url": embed_url,
            "origin": _origin_from(public_url),
            "xml": diagram.xml or "<mxGraphModel/>",
            "save_xml_url": reverse("diagrams:save_xml", args=[diagram.pk]),
            "save_thumbnail_url": reverse("diagrams:save_thumbnail", args=[diagram.pk]),
        },
    }
    return JsonResponse(payload)


@login_required
def diagram_viewer_context(request, pk: int):
    diagram = get_object_or_404(Diagram, pk=pk, owner=request.user)
    thumbnail_url = _current_thumbnail_url(diagram)
    if not thumbnail_url and _regenerate_drawio_thumbnail(diagram, diagram.xml or "<mxGraphModel/>"):
        thumbnail_url = _current_thumbnail_url(diagram)
    payload = {
        "ok": True,
        "diagram": {
            "id": diagram.pk,
            "title": diagram.title,
            "thumbnail_url": request.build_absolute_uri(thumbnail_url) if thumbnail_url else None,
        },
    }
    return JsonResponse(payload)


@login_required
@require_POST
def diagram_import_xml(request, pk: int):
    logger.info("TEST")
    diagram = get_object_or_404(Diagram, pk=pk, owner=request.user)
    base_context = _build_import_log_context(request, diagram)
    logger.info(
        "diagram_import_xml: request received diagram_id=%s user_id=%s username=%s",
        base_context["diagram_id"],
        base_context["user_id"],
        base_context["username"],
    )
    uploaded_file = request.FILES.get("file") or request.FILES.get("diagram")
    if uploaded_file is None:
        logger.warning(
            "diagram_import_xml: missing file diagram_id=%s user_id=%s",
            base_context["diagram_id"],
            base_context["user_id"],
        )
        return JsonResponse({"ok": False, "error": "missing_file"}, status=400)
    log_context = _build_import_log_context(request, diagram, uploaded_file)
    logger.info(
        "diagram_import_xml: file received diagram_id=%s user_id=%s filename=%s size=%s content_type=%s",
        log_context["diagram_id"],
        log_context["user_id"],
        log_context.get("file_name"),
        log_context.get("file_size"),
        log_context.get("content_type"),
    )

    raw = uploaded_file.read()
    if not raw:
        logger.warning(
            "diagram_import_xml: empty file diagram_id=%s user_id=%s filename=%s",
            log_context["diagram_id"],
            log_context["user_id"],
            log_context.get("file_name"),
        )
        return JsonResponse({"ok": False, "error": "empty_file"}, status=400)

    try:
        xml_payload = raw.decode("utf-8")
    except UnicodeDecodeError:
        logger.exception(
            "diagram_import_xml: utf-8 decode error diagram_id=%s user_id=%s filename=%s",
            log_context["diagram_id"],
            log_context["user_id"],
            log_context.get("file_name"),
        )
        xml_payload = raw.decode("utf-8", errors="ignore")

    try:
        normalized_xml = validate_drawio_xml(xml_payload)
    except ValidationError as exc:
        message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
        params = getattr(exc, "params", None) or {}
        details = {}
        if isinstance(params, dict):
            raw_tag = params.get("raw_tag")
            tag = params.get("tag")
            if raw_tag or tag:
                details = {"tag": tag, "raw_tag": raw_tag}
        if details:
            logger.warning(
                "diagram_import_xml: validation error diagram_id=%s user_id=%s filename=%s error=%s details=%s",
                log_context["diagram_id"],
                log_context["user_id"],
                log_context.get("file_name"),
                message,
                details,
            )
        else:
            logger.warning(
                "diagram_import_xml: validation error diagram_id=%s user_id=%s filename=%s error=%s",
                log_context["diagram_id"],
                log_context["user_id"],
                log_context.get("file_name"),
                message,
            )
        payload = {"ok": False, "error": "invalid_diagram", "message": message}
        if details:
            payload["details"] = details
        return JsonResponse(payload, status=400)

    diagram.xml = normalized_xml
    diagram.updated_at = timezone.now()
    if diagram.thumbnail:
        diagram.thumbnail.delete(save=False)
        diagram.thumbnail = None
    diagram.save(update_fields=["xml", "thumbnail", "updated_at"])
    regenerated = _regenerate_drawio_thumbnail(diagram, normalized_xml)
    logger.info(
        "diagram_import_xml: thumbnail regeneration diagram_id=%s user_id=%s regenerated=%s",
        log_context["diagram_id"],
        log_context["user_id"],
        regenerated,
    )
    thumbnail_url = _current_thumbnail_url(diagram) if regenerated else None
    if thumbnail_url:
        thumbnail_url = request.build_absolute_uri(thumbnail_url)

    logger.info(
        "diagram_import_xml: success diagram_id=%s user_id=%s filename=%s thumbnail=%s",
        log_context["diagram_id"],
        log_context["user_id"],
        log_context.get("file_name"),
        bool(thumbnail_url),
    )
    return JsonResponse(
        {
            "ok": True,
            "diagram": {
                "id": diagram.pk,
                "title": diagram.title,
                "thumbnail_url": thumbnail_url,
            },
        }
    )


@login_required
def diagram_export_xml(request, pk: int):
    diagram = get_object_or_404(Diagram, pk=pk, owner=request.user)
    xml_payload = diagram.xml or "<mxGraphModel/>"
    filename_root = slugify(diagram.title) or f"diagram-{diagram.pk}"
    response = HttpResponse(xml_payload, content_type="application/xml; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename_root}.drawio"'
    return response
