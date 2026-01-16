from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from typing import Any, Dict

from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import slugify

from cintafactory.seaweedfs_storage import SeaweedFSStorage

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


@lru_cache(maxsize=1)
def get_dat_export_storage() -> SeaweedFSStorage:
    return SeaweedFSStorage()


def store_dat_pdf_export(dat, content: bytes, *, refresh_modified: bool = True) -> str:
    path = get_dat_pdf_export_path(dat)
    storage = get_dat_export_storage()
    if storage.exists(path):
        if refresh_modified:
            storage.delete(path)
        else:
            new_hash = hashlib.sha256(content).hexdigest()
            try:
                with storage.open(path, "rb") as existing:
                    current_hash = hashlib.sha256(existing.read()).hexdigest()
            except Exception:
                current_hash = None
            if current_hash and current_hash == new_hash:
                return path
            storage.delete(path)
    storage.save(path, ContentFile(content))
    dat.pdf_export_path = path
    dat.pdf_export_size = len(content or b"")
    dat.pdf_export_content_type = "application/pdf"
    dat.save(update_fields=["pdf_export_path", "pdf_export_size", "pdf_export_content_type", "updated_at"])
    return path


def dat_pdf_export_exists(dat) -> bool:
    storage = get_dat_export_storage()
    path = dat.pdf_export_path or get_dat_pdf_export_path(dat)
    return storage.exists(path)


def dat_pdf_export_modified_at(dat):
    storage = get_dat_export_storage()
    path = dat.pdf_export_path or get_dat_pdf_export_path(dat)
    if not storage.exists(path):
        return None
    try:
        modified = storage.get_modified_time(path)
    except (OSError, NotImplementedError):
        return None
    return timezone.localtime(modified)


def open_dat_pdf_export(dat):
    storage = get_dat_export_storage()
    path = dat.pdf_export_path or get_dat_pdf_export_path(dat)
    if not storage.exists(path):
        return None
    return storage.open(path, "rb")
