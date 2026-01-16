from __future__ import annotations

import base64
import copy
import logging
import mimetypes
from typing import Any, Dict, Iterable, List, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.module_loading import import_string

from diagrams.models import Diagram

from .models import (
    DAT,
    DATPart,
    DATPartEntry,
    DATPartEntryType,
    DATSection,
    DATStatus,
    DATSubSection,
)
from .sections import sync_dat_sections_if_needed
from .utils import (
    format_user_display,
    isoformat_datetime,
    localize_datetime,
    serialize_role,
    serialize_user,
)

DEFAULT_DAT_EXPORT_MODEL_BUILDER = "dat.exporters.DATExportModelBuilder"
logger = logging.getLogger(__name__)


def get_dat_export_model_builder():
    """
    Return an instance of the configured DAT export builder.
    """
    builder_path = getattr(settings, "DAT_EXPORT_MODEL_BUILDER", DEFAULT_DAT_EXPORT_MODEL_BUILDER)
    try:
        builder_cls = import_string(builder_path)
    except ImportError as exc:  # pragma: no cover - defensive branch
        raise ImproperlyConfigured(
            f"Cannot import DAT export model builder '{builder_path}': {exc}"
        ) from exc
    return builder_cls()


class DATExportModelBuilder:
    """
    Assemble a serialisable representation of a DAT, ready for JSON or PDF exports.

    Override this class (and reference it via the DAT_EXPORT_MODEL_BUILDER setting)
    to customise the export structure or filtering rules.
    """

    include_empty_parts = True

    def __init__(self):
        self._participant_role_map: Dict[str, Any] = {}

    def build(self, dat: DAT) -> Dict[str, Any]:
        sync_dat_sections_if_needed(dat)
        self._participant_role_map = self._build_participant_map(dat)
        exported_at = timezone.now()
        payload = {
            "dat": self.build_dat_metadata(dat),
            "application": self.build_application(dat),
            "owner": serialize_user(dat.owner),
            "participants": self.build_participants(dat),
            "sections": self.build_sections(dat),
            "exported_at": isoformat_datetime(exported_at),
            "exported_at_display": localize_datetime(exported_at),
        }
        return payload

    def build_dat_metadata(self, dat: DAT) -> Dict[str, Any]:
        return {
            "id": dat.pk,
            "reference": dat.reference,
            "title": dat.title,
            "description": dat.description,
            "status": dat.status,
            "status_label": self.get_status_label(dat.status),
            "created_at": isoformat_datetime(dat.created_at),
            "created_at_display": localize_datetime(dat.created_at),
            "updated_at": isoformat_datetime(dat.updated_at),
            "updated_at_display": localize_datetime(dat.updated_at),
        }

    def build_application(self, dat: DAT) -> Dict[str, Any] | None:
        application = getattr(dat, "application", None)
        if application is None:
            return None
        return {
            "id": application.pk,
            "code": application.code,
            "name": application.name,
            "description": application.description,
        }

    def get_status_label(self, status: str | None) -> str | None:
        if not status:
            return None
        try:
            return DATStatus(status).label
        except ValueError:
            return status

    def build_participants(self, dat: DAT) -> List[Dict[str, Any]]:
        participants = []
        for participant in dat.participants.all():
            user = getattr(participant, "user", None)
            role = getattr(participant, "role", None)
            participants.append(
                {
                    "id": participant.pk,
                    "user": serialize_user(user),
                    "role": serialize_role(role),
                    "user_display": format_user_display(user),
                    "role_label": getattr(role, "name", None),
                    "role_slug": getattr(role, "slug", None),
                    "assigned_at": isoformat_datetime(participant.created_at),
                    "assigned_at_display": localize_datetime(participant.created_at),
                }
            )
        return participants

    def build_sections(self, dat: DAT) -> List[Dict[str, Any]]:
        sections = []
        for section in self._prefetch_sections(dat):
            section_responsibles = self.build_responsibles(
                dat,
                section.allowed_roles.all(),
                fallback_user=dat.owner,
            )
            sub_sections = []
            for sub_section in section.sub_sections.all():
                sub_responsibles = self.build_responsibles(
                    dat,
                    sub_section.allowed_roles.all(),
                    fallback_entries=section_responsibles,
                )
                sub_sections.append(
                    {
                        "id": sub_section.pk,
                        "slug": sub_section.slug,
                        "title": sub_section.title,
                        "description": sub_section.description,
                        "responsibles": sub_responsibles,
                        "parts": self.build_parts(sub_section),
                        "order": sub_section.order,
                    }
                )
            sections.append(
                {
                    "id": section.pk,
                    "slug": section.slug,
                    "title": section.title,
                    "description": section.description,
                    "responsibles": section_responsibles,
                    "sub_sections": sub_sections,
                    "order": section.order,
                }
            )
        return sections

    def build_parts(self, sub_section: DATSubSection) -> List[Dict[str, Any]]:
        parts = []
        for part in sub_section.parts.all():
            value = part.value
            entry = part._get_current_entry()
            has_value = value not in (None, "", [], {}, ())
            is_repeater = part.data_type == DATPartEntryType.REPEATER
            table_columns = self._extract_repeater_columns(part, value) if is_repeater else []
            display_value = part.render_value(value)
            if is_repeater:
                display_value = self._attach_repeater_diagram_previews(part, display_value)
            payload = {
                "id": part.pk,
                "key": part.key,
                "label": part.label,
                "data_type": part.data_type,
                "required": part.required,
                "value": value,
                "display_value": display_value,
                "order": part.order,
                "config": part.config or {},
                "updated_at": isoformat_datetime(getattr(entry, "updated_at", None)),
                "updated_at_display": localize_datetime(getattr(entry, "updated_at", None)),
                "has_value": has_value,
                "is_repeater": is_repeater,
                "table_columns": table_columns,
            }
            if self.include_empty_parts or has_value:
                parts.append(payload)
        return parts

    def build_responsibles(
        self,
        dat: DAT,
        roles: Iterable[Any],
        *,
        fallback_user=None,
        fallback_entries: List[Dict[str, Any]] | None = None,
    ) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for role in roles or []:
            participant = self._participant_role_map.get(getattr(role, "slug", None))
            user = getattr(participant, "user", None)
            entries.append(
                {
                    "role": serialize_role(role),
                    "user": serialize_user(user),
                    "user_display": format_user_display(user),
                    "participant_id": getattr(participant, "pk", None),
                }
            )
        if entries:
            return entries
        if fallback_entries:
            return [copy.deepcopy(entry) for entry in fallback_entries]
        if fallback_user:
            return [
                {
                    "role": None,
                    "user": serialize_user(fallback_user),
                    "user_display": format_user_display(fallback_user),
                    "participant_id": None,
                }
            ]
        return []

    def _build_participant_map(self, dat: DAT) -> Dict[str, Any]:
        participant_map: Dict[str, Any] = {}
        for participant in dat.participants.all():
            role = getattr(participant, "role", None)
            slug = getattr(role, "slug", None)
            if slug:
                participant_map[slug] = participant
        return participant_map

    def _prefetch_sections(self, dat: DAT):
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
        return (
            dat.sections.order_by("order", "id")
            .select_related("metadata")
            .prefetch_related("allowed_roles")
            .prefetch_related(sub_section_prefetch)
        )

    def _extract_repeater_columns(self, part: DATPart, rows) -> List[Dict[str, Any]]:
        config = part.config or {}
        columns = config.get("columns")
        normalized = []
        if isinstance(columns, list):
            for column in columns:
                if not isinstance(column, dict):
                    continue
                key = column.get("key")
                label = column.get("label") or key
                if not key:
                    continue
                normalized.append({"key": key, "label": label})
        elif isinstance(rows, list) and rows:
            sample = rows[0]
            if isinstance(sample, dict):
                for key in sample.keys():
                    label = key.replace("_", " ").title()
                    normalized.append({"key": key, "label": label})
        return normalized

    def _attach_repeater_diagram_previews(self, part: DATPart, rows):
        if not rows or not isinstance(rows, list):
            return rows
        drawio_columns = self._get_drawio_columns(part)
        if not drawio_columns:
            return rows
        diagram_ids = self._collect_diagram_ids(rows, drawio_columns)
        if not diagram_ids:
            return rows
        previews = self._load_diagram_previews(diagram_ids)
        if not previews:
            return rows
        for row in rows:
            if not isinstance(row, dict):
                continue
            for column in drawio_columns:
                column_key = column.get("key")
                diagram_id = self._safe_positive_int(row.get(column_key))
                if diagram_id and diagram_id in previews:
                    diagram_payload = previews[diagram_id]
                    row[f"{column_key}_diagram"] = diagram_payload
                    row.setdefault("drawio_diagram", diagram_payload)
        return rows

    def _get_drawio_columns(self, part: DATPart) -> Sequence[Dict[str, Any]]:
        config = part.config or {}
        columns = config.get("columns")
        if not isinstance(columns, list):
            return ()
        drawio_columns: list[Dict[str, Any]] = []
        for column in columns:
            if not isinstance(column, dict):
                continue
            if column.get("drawio") or column.get("render") == "drawio_diagram":
                drawio_columns.append(column)
        return tuple(drawio_columns)

    def _collect_diagram_ids(self, rows, drawio_columns: Sequence[Dict[str, Any]]):
        diagram_ids: set[int] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            for column in drawio_columns:
                value = row.get(column.get("key"))
                diagram_id = self._safe_positive_int(value)
                if diagram_id:
                    diagram_ids.add(diagram_id)
        return diagram_ids

    def _safe_positive_int(self, raw) -> int | None:
        if raw in (None, ""):
            return None
        try:
            candidate = int(str(raw).strip())
        except (TypeError, ValueError):
            return None
        if candidate < 1:
            return None
        return candidate

    def _load_diagram_previews(self, diagram_ids: Iterable[int]) -> Dict[int, Dict[str, Any]]:
        diagrams = Diagram.objects.filter(pk__in=diagram_ids)
        previews: Dict[int, Dict[str, Any]] = {}
        for diagram in diagrams:
            previews[diagram.pk] = self._build_diagram_preview(diagram)
        return previews

    def _build_diagram_preview(self, diagram: Diagram) -> Dict[str, Any]:
        data_uri = self._thumbnail_data_uri(diagram) or self._generate_drawio_thumbnail(diagram)
        return {
            "id": diagram.pk,
            "title": diagram.title,
            "thumbnail_url": diagram.thumbnail.url if diagram.thumbnail else None,
            "data_uri": data_uri,
            "updated_at": isoformat_datetime(diagram.updated_at),
        }

    def _thumbnail_data_uri(self, diagram: Diagram) -> str | None:
        field = diagram.thumbnail
        if not field:
            return None
        raw = None
        try:
            field.open("rb")
            raw = field.read()
        except FileNotFoundError:
            raw = None
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("Impossible de lire la miniature du diagramme %s: %s", diagram.pk, exc)
            raw = None
        finally:
            try:
                field.close()
            except Exception:  # pragma: no cover - close best effort
                pass
        if not raw:
            return None
        mime_type = mimetypes.guess_type(field.name or "")[0] or "image/png"
        encoded = base64.b64encode(raw).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _generate_drawio_thumbnail(self, diagram: Diagram) -> str | None:
        xml_payload = diagram.read_xml() or "<mxGraphModel/>"
        for export_url in self._get_drawio_export_candidates():
            payload = urlencode(
                {
                    "format": "png",
                    "scale": "1",
                    "xml": xml_payload,
                    "bg": "#ffffff",
                    "base64": "1",
                }
            ).encode("utf-8")
            request = Request(
                export_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            try:
                with urlopen(request, timeout=30) as response:
                    if response.status != 200:
                        raise ValueError(f"HTTP {response.status}")
                    payload_base64 = response.read().decode("utf-8").strip()
            except Exception as exc:  # pragma: no cover - best-effort export fallback
                logger.warning(
                    "Impossible de générer une miniature Draw.io pour le diagramme %s via %s: %s",
                    diagram.pk,
                    export_url,
                    exc,
                )
                continue
            if payload_base64:
                return "data:image/png;base64," + payload_base64
        return None

    def _get_drawio_export_candidates(self) -> List[str]:
        candidates: list[str] = []
        configured = getattr(settings, "DRAWIO_EXPORT_URL", "").rstrip("/")
        if configured:
            candidates.append(configured)
        base_url = getattr(settings, "DRAWIO_BASE_URL", "").rstrip("/")
        fallback = f"{base_url}/export" if base_url else ""
        if fallback and fallback not in candidates:
            candidates.append(fallback)
        return candidates
