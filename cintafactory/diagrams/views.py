import base64
import hashlib
import json
import logging
from time import time
from uuid import uuid4
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_POST, require_http_methods
from django.views.generic import CreateView, DetailView, ListView, TemplateView
from django.templatetags.static import static
from material.frontend.registry import modules as module_registry
from types import SimpleNamespace

from cintafactory.async_jobs import enqueue_drawio_export_job, enqueue_likec4_export_job
from cintafactory.operations.slo_baseline import emit_baseline_metric
from .forms import DiagramForm
from .models import DrawIODiagram, LikeC4Diagram, likec4_png_path_for
from .validation import validate_drawio_xml
from dat.drawio_parser import extract_drawio_pages
from cintafactory.storage.seaweedfs_storage import SeaweedFSStorage
from cintafactory.url_safety import is_http_url


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
        return DrawIODiagram.objects.filter(owner=self.request.user)


class DiagramCreateView(ModuleContextMixin, LoginRequiredMixin, CreateView):
    template_name = "diagrams/create.html"
    form_class = DiagramForm

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.owner = self.request.user
        obj.save()
        obj.write_xml("<mxGraphModel/>")
        return redirect("diagrams:edit", pk=obj.pk)


class DiagramDetailView(ModuleContextMixin, LoginRequiredMixin, DetailView):
    template_name = "diagrams/detail.html"
    model = DrawIODiagram

    def get_queryset(self):
        return DrawIODiagram.objects.filter(owner=self.request.user)


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
        "ui": "atlas",
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


def _normalize_asset_path(raw_path: str | None) -> str:
    if not raw_path:
        return ""
    cleaned = str(raw_path).strip().lstrip("/")
    if not cleaned:
        return ""
    parts = Path(cleaned).parts
    if any(part in (".", "..") for part in parts):
        return ""
    return cleaned


def _split_csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _proxy_path_is_allowed(path: str) -> bool:
    if not path:
        return True
    candidate = str(path).strip()
    if not candidate:
        return True
    lowered = candidate.lower()
    parsed = urlsplit(lowered)
    if parsed.scheme in {"http", "https"} or parsed.netloc or candidate.startswith("/"):
        return False
    if "\x00" in candidate or "\\" in candidate:
        return False
    decoded = unquote(candidate)
    if ".." in decoded:
        return False
    return True


def _proxy_path_matches_prefixes(path: str, prefixes: list[str]) -> bool:
    if not prefixes:
        return True
    normalized = path.lstrip("/")
    for prefix in prefixes:
        if prefix == "*":
            return True
        if normalized == prefix or normalized.startswith(f"{prefix.rstrip('/')}/"):
            return True
    return False


def _proxy_upstream_is_allowlisted(base_url: str, allowed_hosts_setting: str) -> bool:
    parts = urlsplit(base_url)
    host = (parts.hostname or "").strip().lower()
    if not host:
        return False
    if parts.username or parts.password:
        return False
    configured_hosts = {
        host_item.lower()
        for host_item in _split_csv(getattr(settings, allowed_hosts_setting, ""))
        if host_item
    }
    if not configured_hosts:
        configured_hosts = {host}
    return host in configured_hosts


def _diagram_asset_url(request, diagram: DrawIODiagram, storage_path: str | None) -> str | None:
    if not storage_path:
        return None
    prefix = f"diagrams/{diagram.pk}/"
    if not storage_path.startswith(prefix):
        return None
    relative = storage_path[len(prefix) :]
    asset_path = _normalize_asset_path(relative)
    if not asset_path:
        return None
    url = reverse("diagrams:diagram_asset", args=[diagram.pk, asset_path])
    return request.build_absolute_uri(url) if request else url


def _likec4_png_url(request, storage_path: str) -> str:
    base = reverse("diagrams:likec4_png")
    query = urlencode({"file": storage_path})
    url = f"{base}?{query}" if query else base
    return request.build_absolute_uri(url) if request else url


def _current_thumbnail_url(diagram: DrawIODiagram) -> str | None:
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


def _save_thumbnail_from_data_uri(diagram: DrawIODiagram, data_uri: str) -> bool:
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
    diagram.thumbnail_size = len(raw)
    diagram.thumbnail_content_type = "image/png"
    diagram.updated_at = timezone.now()
    diagram.save(update_fields=["thumbnail", "thumbnail_size", "thumbnail_content_type", "updated_at"])
    return True


def _drawio_export_candidates() -> list[str]:
    candidates: list[str] = []
    configured_export = getattr(settings, "DRAWIO_EXPORT_URL", "").rstrip("/")
    if configured_export:
        if is_http_url(configured_export):
            candidates.append(configured_export)
        else:
            logger.warning("DRAWIO_EXPORT_URL ignored: non-http(s) scheme.")
    base_url = getattr(settings, "DRAWIO_BASE_URL", "").rstrip("/")
    if base_url:
        if is_http_url(base_url):
            fallback_export = f"{base_url}/export"
            if fallback_export not in candidates:
                candidates.append(fallback_export)
        else:
            logger.warning("DRAWIO_BASE_URL ignored: non-http(s) scheme.")
    return candidates


def _generate_thumbnail_data_uri_from_drawio(xml_payload: str) -> str | None:
    candidates = _drawio_export_candidates()
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


def _drawio_page_filename(index: int, name: str | None) -> str:
    if name:
        slug = slugify(name)[:40]
        if slug:
            return f"page-{index + 1:02d}-{slug}.png"
    return f"page-{index + 1:02d}.png"


def _export_drawio_png_bytes(xml_payload: str) -> bytes | None:
    candidates = _drawio_export_candidates()
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
        except Exception as exc:  # pragma: no cover - best-effort export fallback
            logger.warning("Impossible de générer une image Draw.io via %s: %s", export_url, exc)
            continue
        if payload_base64:
            try:
                return base64.b64decode(payload_base64)
            except (ValueError, TypeError):
                return None
    return None


def _export_drawio_views(diagram: DrawIODiagram, xml_payload: str) -> bool:
    pages = extract_drawio_pages(xml_payload)
    if not pages:
        return False
    storage = SeaweedFSStorage()
    views_dir = f"diagrams/{diagram.pk}/views"
    old_paths = set(getattr(diagram, "png_paths", []) or [])
    new_paths: list[str] = []
    thumb_bytes = None
    for page in pages:
        page_xml = page.get("xml") or ""
        if not page_xml:
            continue
        png_bytes = _export_drawio_png_bytes(page_xml)
        if not png_bytes:
            continue
        index = int(page.get("index", 0))
        name = page.get("name") or ""
        filename = _drawio_page_filename(index, name)
        path = f"{views_dir}/{filename}"
        content = ContentFile(png_bytes)
        content.content_type = "image/png"
        storage.save(path, content)
        new_paths.append(path)
        if thumb_bytes is None:
            thumb_bytes = png_bytes
    if not new_paths:
        return False
    if thumb_bytes:
        thumb_content = ContentFile(thumb_bytes)
        thumb_content.content_type = "image/png"
        diagram.thumbnail.save("thumb.png", thumb_content, save=False)
        diagram.thumbnail_size = len(thumb_bytes)
        diagram.thumbnail_content_type = "image/png"
    diagram.png_paths = new_paths
    diagram.updated_at = timezone.now()
    diagram.save(update_fields=["thumbnail", "thumbnail_size", "thumbnail_content_type", "png_paths", "updated_at"])
    if getattr(settings, "DRAWIO_EXPORT_DELETE_OLD", True):
        to_delete = old_paths - set(new_paths)
        if to_delete:
            for path in sorted(to_delete):
                try:
                    storage.delete(path)
                except Exception as exc:  # pragma: no cover - best effort cleanup
                    logger.warning("drawio export failed to delete old png %s: %s", path, exc)
    return True


def _regenerate_drawio_thumbnail(diagram: DrawIODiagram, xml_payload: str) -> bool:
    return _export_drawio_views(diagram, xml_payload) or bool(
        _save_thumbnail_from_data_uri(diagram, _generate_thumbnail_data_uri_from_drawio(xml_payload) or "")
    )


def _request_same_origin(request) -> bool:
    expected_scheme = "https" if request.is_secure() else "http"
    expected = f"{expected_scheme}://{request.get_host()}"
    origin = request.headers.get("Origin")
    if origin:
        return origin == expected
    referer = request.headers.get("Referer")
    if not referer:
        return False
    parts = urlsplit(referer)
    referer_origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    return referer_origin == expected


def _reject_unsafe_session_request(request, surface: str):
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return None
    if _request_same_origin(request):
        return None
    logger.warning("%s blocked unsafe session request: cross-origin or missing origin", surface)
    return JsonResponse({"ok": False, "error": "csrf_failed"}, status=403)


class DiagramEditView(ModuleContextMixin, LoginRequiredMixin, TemplateView):
    template_name = "diagrams/edit.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        diagram = get_object_or_404(DrawIODiagram, pk=kwargs["pk"], owner=self.request.user)
        context["diagram"] = diagram
        context["diagram_xml"] = diagram.read_xml()
        library_urls = _collect_library_urls(self.request)
        public_url = _resolve_public_drawio_url(self.request)
        context["drawio_embed_url"] = _build_embed_url(library_urls, public_url, self.request)
        context["drawio_origin"] = _origin_from(public_url)
        return context


@login_required
@require_POST
def diagram_save_xml(request, pk: int):
    diagram = get_object_or_404(DrawIODiagram, pk=pk, owner=request.user)
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid payload"}, status=400)

    xml = data.get("xml", "")
    if not isinstance(xml, str):
        return JsonResponse({"ok": False, "error": "invalid xml"}, status=400)

    diagram.write_xml(xml)
    job = enqueue_drawio_export_job(diagram.pk, xml_payload=xml, requested_by=request.user, source="save_xml")
    status_path = reverse("api:async-job-detail", args=[job.id])
    return JsonResponse(
        {
            "ok": True,
            "job": {
                "job_id": str(job.id),
                "status": job.status,
                "status_url": request.build_absolute_uri(status_path),
            },
        }
    )


@csrf_exempt
@require_POST
def likec4_metadata(request):
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        logger.warning("likec4_metadata invalid payload (json decode error)")
        return JsonResponse({"ok": False, "error": "invalid payload"}, status=400)
    if not isinstance(data, dict):
        logger.warning("likec4_metadata invalid payload (json type)")
        return JsonResponse({"ok": False, "error": "invalid payload"}, status=400)

    token = getattr(settings, "LIKEC4_METADATA_TOKEN", "")
    user = getattr(request, "user", None)
    is_authenticated = bool(getattr(user, "is_authenticated", False))
    provided = request.headers.get("X-LikeC4-Token", "") or request.GET.get("token", "") or data.get("token", "")
    token_valid = bool(token) and str(provided or "").strip() == str(token or "").strip()
    if not (is_authenticated or token_valid):
        emit_baseline_metric(
            "auth.token_validation",
            duration_ms=0.0,
            success=False,
            dimensions={
                "surface": "likec4_metadata",
                "outcome": "unauthorized",
            },
        )
        logger.warning(
            "likec4_metadata unauthorized: auth=%s has_header=%s has_query=%s has_body=%s user_agent=%s",
            is_authenticated,
            bool(request.headers.get("X-LikeC4-Token", "")),
            bool(request.GET.get("token", "")),
            bool(data.get("token")),
            request.headers.get("User-Agent", ""),
        )
        return JsonResponse({"ok": False, "error": "unauthorized"}, status=403)
    if is_authenticated and not token_valid:
        csrf_response = _reject_unsafe_session_request(request, "likec4_metadata")
        if csrf_response is not None:
            return csrf_response
    path = data.get("path")
    storage_path = _normalize_likec4_path(path if isinstance(path, str) else None)
    if not storage_path:
        logger.warning("likec4_metadata missing/invalid path: %s", path)
        return JsonResponse({"ok": False, "error": "missing path"}, status=400)
    size = data.get("size") or 0
    try:
        size_value = int(size)
    except (TypeError, ValueError):
        size_value = 0
    content_type = data.get("content_type") or ""
    defaults = {
        "content_type": str(content_type or ""),
        "size": max(size_value, 0),
        "updated_at": timezone.now(),
    }

    png_path_raw = data.get("png_path")
    png_path = _normalize_likec4_asset_path(png_path_raw if isinstance(png_path_raw, str) else None, ".png")
    if png_path_raw and not png_path:
        logger.warning("likec4_metadata invalid png path: %s", png_path_raw)
        return JsonResponse({"ok": False, "error": "invalid png path"}, status=400)
    if png_path:
        png_size = data.get("png_size") or 0
        try:
            png_size_value = int(png_size)
        except (TypeError, ValueError):
            png_size_value = 0
        png_content_type = data.get("png_content_type") or "image/png"
        defaults.update(
            {
                "png_path": png_path,
                "png_size": max(png_size_value, 0),
                "png_content_type": str(png_content_type or "image/png"),
                "png_updated_at": timezone.now(),
            }
        )

    png_paths_raw = data.get("png_paths")
    if isinstance(png_paths_raw, list):
        normalized_paths = []
        seen = set()
        for item in png_paths_raw:
            normalized = _normalize_likec4_asset_path(item if isinstance(item, str) else None, ".png")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            normalized_paths.append(normalized)
        defaults["png_paths"] = normalized_paths

    existing = LikeC4Diagram.objects.filter(storage_path=storage_path).only("png_path", "png_paths").first()
    old_paths = set()
    if existing and existing.png_path:
        old_paths.add(existing.png_path)
    if existing and isinstance(existing.png_paths, list):
        for entry in existing.png_paths:
            if isinstance(entry, str) and entry:
                old_paths.add(entry)

    LikeC4Diagram.objects.update_or_create(storage_path=storage_path, defaults=defaults)
    logger.info(
        "likec4_metadata updated: path=%s size=%s png_path=%s",
        storage_path,
        defaults.get("size"),
        defaults.get("png_path"),
    )
    new_paths = set()
    if png_path:
        new_paths.add(png_path)
    if isinstance(png_paths_raw, list):
        normalized_paths = defaults.get("png_paths") or []
        for entry in normalized_paths:
            if isinstance(entry, str) and entry:
                new_paths.add(entry)
    if new_paths and getattr(settings, "LIKEC4_EXPORT_DELETE_OLD", True):
        to_delete = old_paths - new_paths
        if to_delete:
            storage = SeaweedFSStorage()
            for path in sorted(to_delete):
                try:
                    storage.delete(path)
                except Exception as exc:  # pragma: no cover - best effort cleanup
                    logger.warning("likec4_metadata failed to delete old png %s: %s", path, exc)

    job_payload = None
    if not png_path:
        job = enqueue_likec4_export_job(
            storage_path,
            requested_by=user if is_authenticated else None,
            source="metadata",
        )
        status_path = reverse("api:async-job-detail", args=[job.id])
        job_payload = {
            "job_id": str(job.id),
            "status": job.status,
            "status_url": request.build_absolute_uri(status_path),
        }
    response = {"ok": True}
    if job_payload:
        response["job"] = job_payload
    return JsonResponse(response)


def _normalize_likec4_path(raw_path: str | None) -> str:
    return _normalize_likec4_asset_path(raw_path, ".c4")


def _normalize_likec4_asset_path(raw_path: str | None, suffix: str) -> str:
    if not raw_path:
        return ""
    cleaned = str(raw_path).strip().lstrip("/")
    if not cleaned:
        return ""
    parts = Path(cleaned).parts
    if any(part in (".", "..") for part in parts):
        return ""
    if suffix and not cleaned.lower().endswith(suffix):
        return ""
    return cleaned


@login_required
@require_POST
def likec4_import(request):
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return JsonResponse({"ok": False, "error": "missing_file"}, status=400)
    filename = uploaded_file.name or "diagram.c4"
    if not filename.lower().endswith(".c4"):
        return JsonResponse({"ok": False, "error": "invalid_extension"}, status=400)

    requested_path = request.POST.get("path")
    storage_path = _normalize_likec4_path(requested_path)
    if not storage_path:
        unique_id = f"{int(time() * 1000)}{uuid4().hex[:4]}"
        storage_path = f"diagrams/{unique_id}/likec4.c4"

    content_type = getattr(uploaded_file, "content_type", "") or "text/plain"
    storage = SeaweedFSStorage()
    try:
        storage.save(storage_path, uploaded_file)
    except HTTPError as exc:
        logger.warning("LikeC4 import failed for %s: %s", storage_path, exc)
        return JsonResponse({"ok": False, "error": "storage_failed"}, status=502)

    size = int(getattr(uploaded_file, "size", 0) or 0)
    LikeC4Diagram.objects.update_or_create(
        storage_path=storage_path,
        defaults={
            "content_type": content_type,
            "size": max(size, 0),
            "updated_at": timezone.now(),
        },
    )
    job = enqueue_likec4_export_job(storage_path, requested_by=request.user, source="import")
    status_path = reverse("api:async-job-detail", args=[job.id])
    return JsonResponse(
        {
            "ok": True,
            "path": storage_path,
            "size": size,
            "content_type": content_type,
            "job_id": str(job.id),
            "status": job.status,
            "status_url": request.build_absolute_uri(status_path),
        }
    )


@login_required
@require_http_methods(["GET", "HEAD"])
def likec4_png(request):
    raw_path = request.GET.get("file")
    png_path = _normalize_likec4_asset_path(raw_path, ".png")
    c4_path = _normalize_likec4_path(raw_path)
    if not png_path and not c4_path:
        return HttpResponseBadRequest("Invalid LikeC4 file path.")
    if not png_path and c4_path:
        png_path = likec4_png_path_for(c4_path)

    storage_path = png_path
    storage = SeaweedFSStorage()
    file_meta = None
    if c4_path:
        file_meta = LikeC4Diagram.objects.filter(storage_path=c4_path).only("png_path", "png_content_type").first()
    if not file_meta and png_path:
        file_meta = LikeC4Diagram.objects.filter(png_path=png_path).only("png_path", "png_content_type").first()
    if file_meta and file_meta.png_path:
        storage_path = file_meta.png_path
    try:
        exists = storage.exists(storage_path)
    except Exception as exc:
        logger.warning("LikeC4 PNG lookup failed for %s: %s", storage_path, exc)
        raise Http404("LikeC4 PNG not found.")
    if not exists:
        raise Http404("LikeC4 PNG not found.")

    try:
        file_handle = storage.open(storage_path, "rb")
    except FileNotFoundError:
        raise Http404("LikeC4 PNG not found.")
    content_type = "image/png"
    if file_meta and file_meta.png_content_type:
        content_type = file_meta.png_content_type
    response = FileResponse(file_handle, content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
def likec4_views(request):
    raw_path = request.GET.get("file")
    storage_path = _normalize_likec4_path(raw_path)
    if not storage_path:
        return HttpResponseBadRequest("Invalid LikeC4 file path.")
    file_meta = LikeC4Diagram.objects.filter(storage_path=storage_path).only("png_path", "png_paths").first()
    paths = []
    thumb_url = None
    thumb_path = file_meta.png_path if file_meta and file_meta.png_path else None
    if thumb_path:
        thumb_url = _likec4_png_url(request, thumb_path)
    if file_meta and isinstance(file_meta.png_paths, list):
        seen = set()
        for entry in file_meta.png_paths:
            normalized = _normalize_likec4_asset_path(entry if isinstance(entry, str) else None, ".png")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            url = _likec4_png_url(request, normalized)
            if thumb_url and url == thumb_url:
                continue
            paths.append(url)
    if not paths:
        fallback_path = likec4_png_path_for(storage_path)
        paths = [_likec4_png_url(request, fallback_path)]
    thumb_path = thumb_path or likec4_png_path_for(storage_path)
    return JsonResponse(
        {
            "ok": True,
            "paths": paths,
            "thumbnail_url": _likec4_png_url(request, thumb_path),
        }
    )


@login_required
def likec4_export(request):
    storage_path = _normalize_likec4_path(request.GET.get("file"))
    if not storage_path:
        return HttpResponseBadRequest("Invalid LikeC4 file path.")

    storage = SeaweedFSStorage()
    file_meta = LikeC4Diagram.objects.filter(storage_path=storage_path).only("content_type").first()
    content_type = file_meta.content_type if file_meta and file_meta.content_type else "text/plain"
    if content_type.startswith("text/") and "charset=" not in content_type:
        content_type = f"{content_type}; charset=utf-8"

    try:
        file_handle = storage.open(storage_path, "rb")
    except FileNotFoundError:
        raise Http404("LikeC4 file not found.")

    filename = Path(storage_path).name or "diagram.c4"
    response = FileResponse(file_handle, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_http_methods(["GET", "HEAD"])
def diagram_asset(request, pk: int, asset_path: str):
    diagram = get_object_or_404(DrawIODiagram, pk=pk, owner=request.user)
    normalized = _normalize_asset_path(asset_path)
    if not normalized:
        raise Http404("Diagram asset not found.")
    storage_path = f"diagrams/{diagram.pk}/{normalized}"
    allowed = set(diagram.png_paths or [])
    thumb_name = diagram.thumbnail.name if diagram.thumbnail and diagram.thumbnail.name else ""
    if thumb_name:
        allowed.add(thumb_name)
    if storage_path not in allowed:
        raise Http404("Diagram asset not found.")
    storage = SeaweedFSStorage()
    try:
        file_handle = storage.open(storage_path, "rb")
    except FileNotFoundError:
        raise Http404("Diagram asset not found.")
    content_type = "image/png"
    if thumb_name and storage_path == thumb_name:
        content_type = diagram.thumbnail_content_type or "image/png"
    response = FileResponse(file_handle, content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_POST
def diagram_save_thumbnail(request, pk: int):
    diagram = get_object_or_404(DrawIODiagram, pk=pk, owner=request.user)
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid payload"}, status=400)

    data_uri = data.get("data_uri")
    if not _save_thumbnail_from_data_uri(diagram, data_uri):
        return JsonResponse({"ok": False, "error": "expected PNG data URI"}, status=400)
    thumbnail_url = _diagram_asset_url(request, diagram, diagram.thumbnail.name)
    return JsonResponse({"ok": True, "thumbnail_url": thumbnail_url})


@require_http_methods(["GET", "HEAD"])
@xframe_options_exempt
def drawio_proxy(request, path: str = ""):
    """
    Lightweight reverse proxy to expose the draw.io service over HTTPS.
    """
    upstream_base = settings.DRAWIO_BASE_URL.rstrip("/")
    if not is_http_url(upstream_base):
        logger.warning("draw.io proxy blocked: DRAWIO_BASE_URL must be http(s).")
        raise Http404("draw.io unavailable")
    if not _proxy_upstream_is_allowlisted(upstream_base, "DRAWIO_PROXY_ALLOWED_UPSTREAM_HOSTS"):
        logger.warning("draw.io proxy blocked: upstream host is not allowlisted.")
        raise Http404("draw.io unavailable")
    normalized_path = (path or "").strip()
    allowed_prefixes = _split_csv(getattr(settings, "DRAWIO_PROXY_ALLOWED_PATH_PREFIXES", "*,"))
    if not _proxy_path_is_allowed(normalized_path) or not _proxy_path_matches_prefixes(normalized_path, allowed_prefixes):
        logger.warning("draw.io proxy blocked: invalid/disallowed path '%s'.", normalized_path)
        raise Http404("draw.io unavailable")
    upstream = upstream_base if not normalized_path else f"{upstream_base}/{normalized_path.lstrip('/')}"
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


@xframe_options_exempt
@ensure_csrf_cookie
@csrf_exempt
@login_required
@require_http_methods(["GET", "HEAD", "POST"])
def likec4_proxy(request, path: str = ""):
    """
    Reverse proxy for the LikeC4 editor UI/API behind authenticated Django sessions.
    """
    upstream_base = getattr(settings, "LIKEC4_EDITOR_URL", "").rstrip("/")
    if not upstream_base:
        raise Http404("LikeC4 editor unavailable.")
    if not is_http_url(upstream_base):
        logger.warning("LikeC4 proxy blocked: LIKEC4_EDITOR_URL must be http(s).")
        raise Http404("LikeC4 editor unavailable.")
    if not _proxy_upstream_is_allowlisted(upstream_base, "LIKEC4_PROXY_ALLOWED_UPSTREAM_HOSTS"):
        logger.warning("LikeC4 proxy blocked: upstream host is not allowlisted.")
        raise Http404("LikeC4 editor unavailable.")
    normalized_path = (path or "").strip()
    allowed_prefixes = _split_csv(getattr(settings, "LIKEC4_PROXY_ALLOWED_PATH_PREFIXES", "*,"))
    if not _proxy_path_is_allowed(normalized_path) or not _proxy_path_matches_prefixes(normalized_path, allowed_prefixes):
        logger.warning("LikeC4 proxy blocked: invalid/disallowed path '%s'.", normalized_path)
        raise Http404("LikeC4 editor unavailable.")
    upstream = upstream_base if not normalized_path else f"{upstream_base}/{normalized_path.lstrip('/')}"
    query = request.META.get("QUERY_STRING")
    if query:
        upstream = f"{upstream}?{query}"

    method = "HEAD" if request.method == "HEAD" else request.method
    csrf_response = _reject_unsafe_session_request(request, "likec4_proxy")
    if csrf_response is not None:
        return csrf_response
    headers = {}
    content_type = request.headers.get("Content-Type")
    if content_type:
        headers["Content-Type"] = content_type
    accept = request.headers.get("Accept")
    if accept:
        headers["Accept"] = accept
    user_agent = request.headers.get("User-Agent")
    if user_agent:
        headers["User-Agent"] = user_agent
    api_token = getattr(settings, "LIKEC4_API_TOKEN", "")
    if api_token:
        headers["X-LikeC4-Token"] = api_token
    body = request.body if method == "POST" else None
    if method == "POST":
        max_body_bytes = int(getattr(settings, "LIKEC4_PROXY_MAX_BODY_BYTES", 1024 * 1024))
        if len(body or b"") > max_body_bytes:
            logger.warning(
                "LikeC4 proxy blocked: payload exceeds max size (%s bytes).",
                max_body_bytes,
            )
            return HttpResponse("payload too large", status=413)

    try:
        req = Request(upstream, data=body, headers=headers, method=method)
        with urlopen(req, timeout=20) as resp:
            status = getattr(resp, "status", 200)
            payload = b"" if method == "HEAD" else resp.read()
            response = HttpResponse(payload, status=status)
            content_type = resp.headers.get("Content-Type")
            if content_type:
                response["Content-Type"] = content_type
            for header_name in ("Cache-Control", "ETag", "Last-Modified", "Expires"):
                header_val = resp.headers.get(header_name)
                if header_val:
                    response[header_name] = header_val
            return response
    except Exception as exc:  # pragma: no cover - network/runtime failures
        logger.warning("likec4 proxy failed for %s: %s", upstream, exc)
        raise Http404("LikeC4 editor unavailable.")


@login_required
def diagram_embed_context(request, pk: int):
    diagram = get_object_or_404(DrawIODiagram, pk=pk, owner=request.user)
    library_urls = _collect_library_urls(request)
    public_url = _resolve_public_drawio_url(request)
    embed_url = _build_embed_url(library_urls, public_url, request)
    diagram_xml = diagram.read_xml() or "<mxGraphModel/>"
    payload = {
        "ok": True,
        "diagram": {"id": diagram.pk, "title": diagram.title},
        "drawio": {
            "embed_url": embed_url,
            "origin": _origin_from(public_url),
            "xml": diagram_xml,
            "save_xml_url": reverse("diagrams:save_xml", args=[diagram.pk]),
            "save_thumbnail_url": reverse("diagrams:save_thumbnail", args=[diagram.pk]),
        },
    }
    return JsonResponse(payload)


@login_required
def diagram_viewer_context(request, pk: int):
    diagram = get_object_or_404(DrawIODiagram, pk=pk, owner=request.user)
    thumbnail_url = _current_thumbnail_url(diagram)
    diagram_xml = diagram.read_xml() or "<mxGraphModel/>"
    drawio_job = None
    if not thumbnail_url:
        drawio_job = enqueue_drawio_export_job(
            diagram.pk,
            xml_payload=diagram_xml,
            requested_by=request.user,
            source="viewer_context",
        )
    thumbnail_url = (
        _diagram_asset_url(request, diagram, diagram.thumbnail.name)
        if thumbnail_url and diagram.thumbnail and diagram.thumbnail.name
        else None
    )
    image_urls = []
    if isinstance(diagram.png_paths, list) and diagram.png_paths:
        seen = set()
        for path in diagram.png_paths:
            if not isinstance(path, str) or not path:
                continue
            url = _diagram_asset_url(request, diagram, path)
            if not url or url in seen:
                continue
            seen.add(url)
            image_urls.append(url)
    if not image_urls and thumbnail_url:
        image_urls = [thumbnail_url]
    payload = {
        "ok": True,
        "diagram": {
            "id": diagram.pk,
            "title": diagram.title,
            "thumbnail_url": thumbnail_url,
            "image_urls": image_urls,
        },
    }
    if drawio_job:
        status_path = reverse("api:async-job-detail", args=[drawio_job.id])
        payload["job"] = {
            "job_id": str(drawio_job.id),
            "status": drawio_job.status,
            "status_url": request.build_absolute_uri(status_path),
        }
    return JsonResponse(payload)


@login_required
@require_POST
def diagram_import_xml(request, pk: int):
    diagram = get_object_or_404(DrawIODiagram, pk=pk, owner=request.user)
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
    content_type = str(getattr(uploaded_file, "content_type", "") or "")
    file_name = str(getattr(uploaded_file, "name", "") or "")
    if content_type == "image/svg+xml" or file_name.lower().endswith(".svg"):
        logger.warning(
            "diagram_import_xml: invalid payload type diagram_id=%s user_id=%s filename=%s content_type=%s",
            base_context["diagram_id"],
            base_context["user_id"],
            file_name,
            content_type,
        )
        return JsonResponse({"ok": False, "error": "invalid_diagram"}, status=400)
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

    content_type = str(getattr(uploaded_file, "content_type", "") or "") or "application/xml"
    diagram.write_xml(normalized_xml, content_type=content_type)
    if diagram.thumbnail:
        diagram.thumbnail.delete(save=False)
        diagram.thumbnail = None
    diagram.thumbnail_size = 0
    diagram.thumbnail_content_type = ""
    diagram.save(update_fields=["thumbnail", "thumbnail_size", "thumbnail_content_type"])
    drawio_job = enqueue_drawio_export_job(
        diagram.pk,
        xml_payload=normalized_xml,
        requested_by=request.user,
        source="import_xml",
    )
    thumbnail_url = None

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
            "job": {
                "job_id": str(drawio_job.id),
                "status": drawio_job.status,
                "status_url": request.build_absolute_uri(reverse("api:async-job-detail", args=[drawio_job.id])),
            },
        }
    )


@login_required
def diagram_export_xml(request, pk: int):
    diagram = get_object_or_404(DrawIODiagram, pk=pk, owner=request.user)
    xml_payload = diagram.read_xml() or "<mxGraphModel/>"
    filename_root = slugify(diagram.title) or f"diagram-{diagram.pk}"
    response = HttpResponse(xml_payload, content_type="application/xml; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename_root}.drawio"'
    return response
