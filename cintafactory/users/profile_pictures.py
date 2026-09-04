from __future__ import annotations

import io
import os
import uuid
from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile, UploadedFile
from django.utils.text import get_valid_filename, slugify
from PIL import Image, ImageOps

from cintafactory.storage.seaweedfs_storage import SeaweedFSStorage

PROFILE_PICTURE_SIZE = (350, 350)
PROFILE_PICTURE_STORAGE_SUBDIR = "profile_pictures"
ALLOWED_PROFILE_PICTURE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
FORMAT_BY_EXTENSION = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
CONTENT_TYPE_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
DEFAULT_PROFILE_EXTENSION = ".jpg"


@lru_cache(maxsize=1)
def get_profile_picture_storage() -> SeaweedFSStorage:
    return SeaweedFSStorage(public_url=settings.SEAWEEDFS_PUBLIC_URL_PP)


def _extract_extension(filename: str) -> str:
    base_name = os.path.basename(filename or "").strip()
    if not base_name:
        return ""
    safe_name = get_valid_filename(base_name).strip().strip(".")
    if not safe_name:
        return ""
    _, ext = os.path.splitext(safe_name)
    return ext.lower()


def build_profile_picture_storage_name(instance, filename: str) -> str:
    ext = _extract_extension(filename)
    if ext not in ALLOWED_PROFILE_PICTURE_EXTENSIONS:
        ext = DEFAULT_PROFILE_EXTENSION
    token = uuid.uuid4().hex
    if getattr(instance, "pk", None):
        user_segment = str(instance.pk)
    else:
        user_segment = slugify(getattr(instance, "username", "") or "user") or "user"
    return f"{PROFILE_PICTURE_STORAGE_SUBDIR}/{user_segment}/{token}{ext}"


def _resolve_format(ext: str) -> tuple[str, str]:
    if ext not in FORMAT_BY_EXTENSION:
        raise ValidationError("L'extension du fichier n'est pas autorisee.")
    return FORMAT_BY_EXTENSION[ext], CONTENT_TYPE_BY_EXTENSION[ext]


def process_profile_picture_upload(
    uploaded_file: UploadedFile,
    *,
    field_name: str = "profile_picture",
) -> UploadedFile:
    if not uploaded_file:
        return uploaded_file
    ext = _extract_extension(uploaded_file.name)
    image_format, content_type = _resolve_format(ext)
    try:
        uploaded_file.seek(0)
    except OSError:
        pass
    try:
        image = Image.open(uploaded_file)
    except Exception as exc:  # pragma: no cover - defensive guard for invalid images
        raise ValidationError("Le fichier n'est pas une image valide.") from exc
    image = ImageOps.exif_transpose(image)
    image = ImageOps.fit(image, PROFILE_PICTURE_SIZE, Image.Resampling.LANCZOS)
    if image_format == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    buffer = io.BytesIO()
    save_kwargs = {"format": image_format}
    if image_format == "JPEG":
        save_kwargs.update({"quality": 90, "optimize": True})
    elif image_format == "PNG":
        save_kwargs.update({"optimize": True})
    elif image_format == "WEBP":
        save_kwargs.update({"quality": 90, "method": 6})
    image.save(buffer, **save_kwargs)
    buffer.seek(0)
    size = buffer.getbuffer().nbytes
    return InMemoryUploadedFile(
        buffer,
        field_name,
        uploaded_file.name,
        content_type,
        size,
        None,
    )
