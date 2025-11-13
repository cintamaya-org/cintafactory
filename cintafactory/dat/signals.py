from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from cintafactory.logging_utils import get_request_context, log_info

from .models import DAT, DATHistory, DATHistoryAction
from .sections import ensure_default_sections

TRACKED_FIELDS = ("title", "description", "status", "owner_id")


def _preview(text: Optional[str], *, length: int = 200) -> Optional[str]:
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    if len(text) <= length:
        return text
    return f"{text[: length - 3]}..."


def _snapshot(instance: DAT) -> Dict[str, Any]:
    owner = getattr(instance, "owner", None)
    return {
        "reference": instance.reference,
        "title": instance.title,
        "description": instance.description,
        "description_preview": _preview(instance.description),
        "status": instance.status,
        "status_label": instance.get_status_display(),
        "owner_id": instance.owner_id,
        "owner_username": getattr(owner, "username", None),
    }


def _display_name(user) -> str:
    if user is None:
        return ""
    if hasattr(user, "get_full_name"):
        full_name = user.get_full_name()
        if full_name:
            return full_name
    if hasattr(user, "get_username"):
        return user.get_username()
    return str(user)


def _resolve_history_actor(instance: DAT) -> Tuple[Optional[Any], str]:
    explicit_actor = getattr(instance, "_history_actor", None)
    if hasattr(instance, "_history_actor"):
        delattr(instance, "_history_actor")
    if explicit_actor is not None:
        return explicit_actor, _display_name(explicit_actor)

    context = get_request_context()
    user_id = context.get("user_id")
    username = context.get("username")
    actor = None
    if user_id:
        UserModel = get_user_model()
        actor = UserModel._default_manager.filter(pk=user_id).first()
        if not username and actor is not None:
            username = _display_name(actor)
    return actor, username or ""


def _create_history_entry(
    *,
    instance: DAT,
    action: DATHistoryAction,
    actor,
    actor_display: str,
    status_before: Optional[str] = None,
    status_after: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    payload = details or None
    DATHistory.objects.create(
        dat=instance,
        action=action,
        status_before=status_before,
        status_after=status_after,
        performed_by=actor if actor is not None else None,
        performed_by_display=actor_display or "",
        details=payload,
    )


@receiver(pre_save, sender=DAT)
def capture_original_dat_state(sender, instance: DAT, **kwargs) -> None:
    """
    Store a lightweight copy of the previous DAT state before updates so that
    we can diff changes once the save completes.
    """
    if not instance.pk:
        instance._original_dat_snapshot = None  # type: ignore[attr-defined]
        return
    try:
        original = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._original_dat_snapshot = None  # type: ignore[attr-defined]
    else:
        instance._original_dat_snapshot = _snapshot(original)  # type: ignore[attr-defined]


@receiver(post_save, sender=DAT)
def log_dat_save(sender, instance: DAT, created: bool, **kwargs) -> None:
    snapshot = _snapshot(instance)
    base_fields = {
        "dat_id": instance.pk,
        "reference": snapshot["reference"],
        "title": snapshot["title"],
        "status": snapshot["status"],
        "status_label": snapshot["status_label"],
        "owner_id": snapshot["owner_id"],
        "owner_username": snapshot["owner_username"],
    }
    if snapshot["description_preview"]:
        base_fields["description_preview"] = snapshot["description_preview"]

    actor, actor_display = _resolve_history_actor(instance)

    if created:
        ensure_default_sections(instance)
        log_info("DAT created", **base_fields)
        _create_history_entry(
            instance=instance,
            action=DATHistoryAction.CREATED,
            actor=actor,
            actor_display=actor_display,
            status_after=snapshot["status"],
        )
        if hasattr(instance, "_original_dat_snapshot"):
            delattr(instance, "_original_dat_snapshot")
        return

    original = getattr(instance, "_original_dat_snapshot", None)
    if original is None:
        log_info("DAT updated", **base_fields)
        if hasattr(instance, "_original_dat_snapshot"):
            delattr(instance, "_original_dat_snapshot")
        return

    changes: Dict[str, Dict[str, Any]] = {}
    for field in TRACKED_FIELDS:
        new_value = snapshot[field]
        old_value = original.get(field)
        if new_value == old_value:
            continue
        if field == "status":
            changes["status"] = {
                "from": original.get("status_label"),
                "to": snapshot["status_label"],
            }
        elif field == "owner_id":
            changes["owner"] = {
                "from_id": original.get("owner_id"),
                "from_username": original.get("owner_username"),
                "to_id": snapshot["owner_id"],
                "to_username": snapshot["owner_username"],
            }
        elif field == "description":
            changes["description"] = {
                "from": original.get("description_preview"),
                "to": snapshot["description_preview"],
            }
        else:
            changes[field] = {"from": original.get(field), "to": new_value}

    if changes:
        base_fields["changes"] = changes

    log_info("DAT updated", **base_fields)

    status_change = changes.get("status")
    owner_change = changes.get("owner")
    other_changes = {
        key: value for key, value in changes.items() if key not in {"status", "owner"}
    }

    if status_change:
        _create_history_entry(
            instance=instance,
            action=DATHistoryAction.STATUS_CHANGED,
            actor=actor,
            actor_display=actor_display,
            status_before=original.get("status"),
            status_after=snapshot["status"],
            details=status_change,
        )

    if owner_change:
        _create_history_entry(
            instance=instance,
            action=DATHistoryAction.OWNER_CHANGED,
            actor=actor,
            actor_display=actor_display,
            status_before=original.get("status"),
            status_after=snapshot["status"],
            details=owner_change,
        )

    if other_changes:
        _create_history_entry(
            instance=instance,
            action=DATHistoryAction.UPDATED,
            actor=actor,
            actor_display=actor_display,
            status_before=original.get("status"),
            status_after=snapshot["status"],
            details={"changes": other_changes},
        )

    if hasattr(instance, "_original_dat_snapshot"):
        delattr(instance, "_original_dat_snapshot")


@receiver(post_delete, sender=DAT)
def log_dat_delete(sender, instance: DAT, **kwargs) -> None:
    snapshot = _snapshot(instance)
    fields = {
        "dat_id": instance.pk,
        "reference": snapshot["reference"],
        "title": snapshot["title"],
        "status": snapshot["status"],
        "status_label": snapshot["status_label"],
        "owner_id": snapshot["owner_id"],
        "owner_username": snapshot["owner_username"],
    }
    if snapshot["description_preview"]:
        fields["description_preview"] = snapshot["description_preview"]
    log_info("DAT deleted", **fields)
