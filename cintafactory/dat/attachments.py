from __future__ import annotations

import logging
import os
import socket
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename, slugify

from cintafactory.seaweedfs_storage import SeaweedFSStorage

from .utils import format_user_display

ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".jpeg",
    ".jpg",
    ".png",
    ".webp",
    ".svg",
    ".ico",
    ".txt",
    ".doc",
    ".docx",
    ".odt",
    ".rtf",
    ".pdf",
    ".md",
    ".xls",
    ".xlsx",
    ".ods",
    ".csv",
    ".tsv",
    ".ppt",
    ".pptx",
    ".odp",
    ".vsdx",
    ".drawio",
}
MAX_ATTACHMENT_SIZE_BYTES = 25 * 1024 * 1024
MAX_ATTACHMENT_SIZE_LABEL = "25 MB"
ATTACHMENT_STORAGE_SUBDIR = "dat_attachments"
ATTACHMENT_NAME_MAX_LENGTH = 200
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AttachmentMetadata:
    original_name: str
    display_name: str
    extension: str
    size: int
    content_type: str


def get_allowed_attachment_extensions() -> list[str]:
    return sorted(ALLOWED_ATTACHMENT_EXTENSIONS)


def get_allowed_attachment_extensions_display() -> str:
    return ", ".join(get_allowed_attachment_extensions())


def get_allowed_attachment_extensions_accept() -> str:
    return ",".join(get_allowed_attachment_extensions())


def build_attachment_ui_context() -> dict[str, object]:
    return {
        "attachments_allowed_extensions": get_allowed_attachment_extensions(),
        "attachments_allowed_extensions_display": get_allowed_attachment_extensions_display(),
        "attachments_accept": get_allowed_attachment_extensions_accept(),
        "attachments_max_size_bytes": MAX_ATTACHMENT_SIZE_BYTES,
        "attachments_max_size_label": MAX_ATTACHMENT_SIZE_LABEL,
    }


def sanitize_attachment_name(filename: str) -> str:
    base_name = os.path.basename(filename or "").strip().replace("\x00", "")
    if not base_name:
        return ""
    safe_name = get_valid_filename(base_name)
    safe_name = safe_name.strip().strip(".")
    if not safe_name:
        return ""
    name_root, ext = os.path.splitext(safe_name)
    if not name_root:
        return ""
    ext = ext.lower()
    safe_name = f"{name_root}{ext}"
    if len(safe_name) > ATTACHMENT_NAME_MAX_LENGTH:
        max_root = ATTACHMENT_NAME_MAX_LENGTH - len(ext)
        safe_name = f"{name_root[:max_root]}{ext}"
    return safe_name


def build_attachment_metadata(uploaded_file) -> AttachmentMetadata:
    if uploaded_file is None:
        raise ValidationError("Aucun fichier transmis.")
    size = int(getattr(uploaded_file, "size", 0) or 0)
    if size > MAX_ATTACHMENT_SIZE_BYTES:
        raise ValidationError(f"Le fichier dépasse la taille maximale autorisée ({MAX_ATTACHMENT_SIZE_LABEL}).")
    original_name = str(getattr(uploaded_file, "name", "") or "")
    display_name = sanitize_attachment_name(original_name)
    if not display_name:
        raise ValidationError("Le nom du fichier est invalide.")
    extension = os.path.splitext(display_name)[1].lower()
    if not extension or extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise ValidationError("L'extension du fichier n'est pas autorisée.")
    content_type = str(getattr(uploaded_file, "content_type", "") or "")
    return AttachmentMetadata(
        original_name=original_name,
        display_name=display_name,
        extension=extension,
        size=size,
        content_type=content_type,
    )


def build_attachment_storage_name(dat_id: int, section_slug: str, display_name: str) -> str:
    token = uuid.uuid4().hex
    safe_slug = slugify(section_slug or "section") or "section"
    return f"{ATTACHMENT_STORAGE_SUBDIR}/{dat_id}/{safe_slug}/{token}_{display_name}"


def build_download_filename(display_name: str, extension: str | None = None) -> str:
    base, ext = os.path.splitext(display_name)
    ext = (extension or ext or "").lower()
    safe_base = slugify(base) or "piece-jointe"
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    return f"{safe_base}{ext}"


def _get_int_setting(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def _get_float_setting(name: str, default: float) -> float:
    try:
        return float(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def _send_clamav_command(host: str, port: int, timeout: int, command: bytes) -> bytes:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(command)
        return sock.recv(4096)


def _probe_clamav(host: str, port: int, timeout: int) -> None:
    for label, command in (
        ("PING", b"PING\n"),
        ("VERSION", b"VERSION\n"),
        ("COMMANDS", b"COMMANDS\n"),
    ):
        try:
            response = _send_clamav_command(host, port, timeout, command)
            text = response.decode("utf-8", errors="replace").strip()
            print(f"[ClamAV] {label} response: {text}", flush=True)
        except OSError as exc:
            print(f"[ClamAV] {label} failed: {exc}", flush=True)


def _scan_file_with_scan_command(uploaded_file, host: str, port: int, timeout: int) -> bytes:
    scan_dir = getattr(settings, "CLAMAV_SCAN_DIR", "") or ""
    if not scan_dir:
        raise ValidationError("Le scan antivirus n'est pas configure (CLAMAV_SCAN_DIR manquant).")
    os.makedirs(scan_dir, exist_ok=True)
    try:
        os.chmod(scan_dir, 0o777)
    except OSError:
        pass
    filename = f"upload_{uuid.uuid4().hex}"
    path = os.path.join(scan_dir, filename)
    uploaded_file.seek(0)
    try:
        with open(path, "wb") as target:
            if hasattr(uploaded_file, "chunks"):
                for chunk in uploaded_file.chunks():
                    target.write(chunk)
            else:
                target.write(uploaded_file.read())
    finally:
        uploaded_file.seek(0)
    print(f"[ClamAV] SCAN path: {path}", flush=True)
    try:
        command = f"SCAN {path}\n".encode("utf-8")
        return _send_clamav_command(host, port, timeout, command)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def scan_file_with_clamav(uploaded_file) -> None:
    host = getattr(settings, "CLAMAV_HOST", "clamav")
    port = _get_int_setting("CLAMAV_PORT", 3310)
    timeout = _get_int_setting("CLAMAV_TIMEOUT", 30)
    retries = _get_int_setting("CLAMAV_RETRY_COUNT", 5)
    delay = _get_float_setting("CLAMAV_RETRY_DELAY", 1.0)
    response = b""
    last_error: Exception | None = None
    response_text = ""
    _probe_clamav(host, port, timeout)
    for attempt in range(retries + 1):
        try:
            print(
                f"[ClamAV] scan attempt {attempt + 1}/{retries + 1} -> {host}:{port} (SCAN)",
                flush=True,
            )
            response = _scan_file_with_scan_command(uploaded_file, host, port, timeout)
            response_text = response.decode("utf-8", errors="replace")
            break
        except ValidationError:
            raise
        except OSError as exc:
            last_error = exc
            logger.warning(
                "ClamAV scan attempt %s/%s failed: %s",
                attempt + 1,
                retries + 1,
                exc,
            )
            print(
                f"[ClamAV] scan attempt {attempt + 1}/{retries + 1} failed: {exc}",
                flush=True,
            )
            if attempt >= retries:
                break
            time.sleep(delay)
    uploaded_file.seek(0)

    if last_error and not response:
        print("[ClamAV] scan failed: service unavailable.", flush=True)
        raise ValidationError("Impossible de verifier le fichier (antivirus indisponible).") from last_error

    if not response_text:
        response_text = response.decode("utf-8", errors="replace")
   
    if "ERROR" in response_text and "No such file or directory" in response_text:
        raise ValidationError("Le fichier n'est pas accessible par l'antivirus (volume partage manquant).")
    if "FOUND" in response_text:
        print(f"[ClamAV] scan result: {response_text.strip()}", flush=True)
        raise ValidationError("Le fichier est infecte et a ete refuse.")
    if "OK" not in response_text:
        logger.warning("ClamAV response unexpected: %s", response_text.strip())
        print(f"[ClamAV] scan unexpected response: {response_text.strip()}", flush=True)
        raise ValidationError("La verification antivirus a echoue.")
    print(f"[ClamAV] scan OK: {response_text.strip()}", flush=True)


@lru_cache(maxsize=1)
def get_attachment_storage() -> SeaweedFSStorage:
    return SeaweedFSStorage()


def create_section_attachment(section, uploaded_file, *, uploaded_by=None):
    from .models import DATSectionAttachment

    metadata = build_attachment_metadata(uploaded_file)
    scan_file_with_clamav(uploaded_file)
    dat_id = getattr(section, "dat_id", None)
    if dat_id is None:
        raise ValidationError("Section invalide pour la piece jointe.")
    storage_name = build_attachment_storage_name(dat_id, section.slug, metadata.display_name)
    storage = get_attachment_storage()
    stored_name = storage.save(storage_name, uploaded_file)
    attachment = DATSectionAttachment(
        section=section,
        storage_path=stored_name,
        original_name=metadata.original_name,
        display_name=metadata.display_name,
        extension=metadata.extension,
        size=metadata.size,
        content_type=metadata.content_type,
        uploaded_by=uploaded_by,
        uploaded_by_display=format_user_display(uploaded_by) if uploaded_by else "",
    )
    try:
        attachment.save()
    except Exception:
        try:
            storage.delete(stored_name)
        except Exception:
            pass
        raise
    return attachment


def delete_section_attachment(attachment) -> None:
    storage = get_attachment_storage()
    path = getattr(attachment, "storage_path", "")
    if path:
        try:
            storage.delete(path)
        except Exception:
            logger.exception("Failed to delete attachment from storage: %s", path)
    attachment.delete()
