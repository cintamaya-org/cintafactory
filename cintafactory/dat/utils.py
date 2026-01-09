from __future__ import annotations

import hashlib
import os
from typing import Any, Dict

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from django.utils.text import slugify


def format_user_display(user) -> str:
    """
    Provide a readable display for any user-like object.
    """
    if user is None:
        return "-"
    if hasattr(user, "get_full_name"):
        full_name = user.get_full_name()
        if full_name:
            return full_name
    if hasattr(user, "get_username"):
        return user.get_username()
    return str(user)


def serialize_user(user) -> Dict[str, Any] | None:
    if user is None:
        return None
    username = user.get_username() if hasattr(user, "get_username") else ""
    full_name = user.get_full_name() if hasattr(user, "get_full_name") else ""
    return {
        "id": getattr(user, "pk", None),
        "username": username,
        "full_name": full_name or "",
        "email": getattr(user, "email", "") or "",
        "display": format_user_display(user),
    }


def serialize_role(role) -> Dict[str, Any] | None:
    if role is None:
        return None
    return {
        "id": getattr(role, "pk", None),
        "slug": getattr(role, "slug", None),
        "name": getattr(role, "name", None),
    }


def localize_datetime(value, fmt: str = "%d/%m/%Y à %Hh%M") -> str:
    if not value:
        return ""
    reference = timezone.localtime(value)
    return reference.strftime(fmt)


def isoformat_datetime(value) -> str | None:
    if not value:
        return None
    reference = timezone.localtime(value)
    return reference.isoformat()


def _dat_pdf_export_basename(dat) -> str:
    base = slugify(getattr(dat, "reference", "") or getattr(dat, "title", "")) or f"dat-{dat.pk}"
    return f"{base}.pdf"


def get_dat_pdf_export_path(dat) -> str:
    basename = _dat_pdf_export_basename(dat)
    return os.path.join("dat_exports", str(dat.pk), basename)


def store_dat_pdf_export(dat, content: bytes, *, refresh_modified: bool = True) -> str:
    path = get_dat_pdf_export_path(dat)
    if default_storage.exists(path):
        if refresh_modified:
            default_storage.delete(path)
        else:
            new_hash = hashlib.sha256(content).hexdigest()
            try:
                with default_storage.open(path, "rb") as existing:
                    current_hash = hashlib.sha256(existing.read()).hexdigest()
            except Exception:
                current_hash = None
            if current_hash and current_hash == new_hash:
                return path
            default_storage.delete(path)
    default_storage.save(path, ContentFile(content))
    return path


def dat_pdf_export_exists(dat) -> bool:
    return default_storage.exists(get_dat_pdf_export_path(dat))


def dat_pdf_export_modified_at(dat):
    path = get_dat_pdf_export_path(dat)
    if not default_storage.exists(path):
        return None
    try:
        modified = default_storage.get_modified_time(path)
    except (OSError, NotImplementedError):
        return None
    return timezone.localtime(modified)


def open_dat_pdf_export(dat):
    path = get_dat_pdf_export_path(dat)
    if not default_storage.exists(path):
        return None
    return default_storage.open(path, "rb")
