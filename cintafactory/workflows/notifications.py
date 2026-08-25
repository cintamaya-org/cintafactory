from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Sequence, Set

from django.db.models import CharField, F, QuerySet, Value
from django.db.models.functions import Cast
from django.http import HttpRequest
from django.utils import timezone

from dat.models import DAT, DATHistory
from dat.permissions import filter_dat_queryset_for_user
from .models import HistoryNotificationSeen, NotificationMessage, NotificationType, UserNotification


DEFAULT_NOTIFICATION_LIMIT = 99
logger = logging.getLogger(__name__)


@dataclass
class NotificationEntry:
    source: str
    history: DATHistory | None = None
    user_notification: UserNotification | None = None
    created_at: datetime | None = None

    def __post_init__(self):
        if self.created_at is None:
            if self.history is not None:
                self.created_at = self.history.performed_at
            elif self.user_notification is not None:
                self.created_at = self.user_notification.created_at

    @property
    def dat(self):
        if self.history is not None:
            return getattr(self.history, "dat", None)
        if self.user_notification is not None:
            return getattr(self.user_notification, "dat", None)
        return None


def _coerce_history_ids(values: Iterable[int]) -> List[int]:
    seen_ids = set()
    coerced: List[int] = []
    for value in values:
        try:
            history_id = int(value)
        except (TypeError, ValueError):
            continue
        if history_id in seen_ids:
            continue
        seen_ids.add(history_id)
        coerced.append(history_id)
    return coerced


def get_seen_notification_ids(
    request: HttpRequest | None,
    *,
    history_ids: Iterable[int] | None = None,
) -> Set[int]:
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return set()
    queryset = HistoryNotificationSeen.objects.filter(user=user)
    if history_ids is not None:
        resolved_ids = _coerce_history_ids(history_ids)
        if not resolved_ids:
            return set()
        queryset = queryset.filter(history_id__in=resolved_ids)
    return set(queryset.values_list("history_id", flat=True))


def mark_notifications_as_seen(request: HttpRequest | None, notification_ids: Iterable[int]) -> None:
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return
    resolved_ids = _coerce_history_ids(notification_ids)
    if not resolved_ids:
        return
    existing_ids = set(DATHistory.objects.filter(pk__in=resolved_ids).values_list("pk", flat=True))
    if not existing_ids:
        return
    HistoryNotificationSeen.objects.bulk_create(
        [HistoryNotificationSeen(user=user, history_id=history_id) for history_id in existing_ids],
        ignore_conflicts=True,
    )


def notification_queryset_for_user(user) -> QuerySet[DATHistory]:
    if not getattr(user, "is_authenticated", False):
        return DATHistory.objects.none()
    dat_queryset = filter_dat_queryset_for_user(DAT.objects.all(), user)
    return DATHistory.objects.filter(dat__in=dat_queryset).order_by("-performed_at", "-id")


def user_notification_queryset(user) -> QuerySet[UserNotification]:
    if not getattr(user, "is_authenticated", False):
        return UserNotification.objects.none()
    return UserNotification.objects.filter(user=user).order_by("-created_at", "-pk")


def fetch_notifications_for_user(
    user,
    *,
    limit: int = DEFAULT_NOTIFICATION_LIMIT,
    offset: int = 0,
    with_related: bool = False,
) -> List[NotificationEntry]:
    offset = max(int(offset), 0)
    limit = max(int(limit), 0)
    if limit == 0:
        return []
    history_queryset = notification_queryset_for_user(user).order_by()
    user_queryset = user_notification_queryset(user).order_by()
    history_rows = history_queryset.annotate(
        source=Value("history", output_field=CharField()),
        source_id=Cast("pk", output_field=CharField()),
        event_at=F("performed_at"),
    ).values("source", "source_id", "event_at")
    user_rows = user_queryset.annotate(
        source=Value("user", output_field=CharField()),
        source_id=Cast("pk", output_field=CharField()),
        event_at=F("created_at"),
    ).values("source", "source_id", "event_at")
    rows = list(
        history_rows.union(user_rows, all=True)
        .order_by("-event_at", "-source_id")[offset : offset + limit]
    )

    history_ids = [row["source_id"] for row in rows if row["source"] == "history"]
    user_ids = [row["source_id"] for row in rows if row["source"] == "user"]
    history_objects = DATHistory.objects.filter(pk__in=history_ids)
    if with_related:
        history_objects = history_objects.select_related("dat", "dat__application", "performed_by")
    history_by_id = {str(entry.pk): entry for entry in history_objects}
    user_objects = UserNotification.objects.filter(pk__in=user_ids)
    if with_related:
        user_objects = user_objects.select_related("dat", "dat__application", "created_by")
    user_by_id = {str(entry.pk): entry for entry in user_objects}

    entries = []
    for row in rows:
        source_id = row["source_id"]
        if row["source"] == "history" and source_id in history_by_id:
            entries.append(NotificationEntry(source="history", history=history_by_id[source_id]))
        elif row["source"] == "user" and source_id in user_by_id:
            entries.append(NotificationEntry(source="user", user_notification=user_by_id[source_id]))
    return entries


def notification_count_for_user(user) -> int:
    """Count both notification sources without loading their payloads."""

    return notification_queryset_for_user(user).order_by().count() + user_notification_queryset(
        user
    ).order_by().count()


def get_unread_notification_count(request: HttpRequest | None, *, limit: int | None = None) -> int:
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return 0
    cache_key = "_workflow_unread_notification_count"
    if limit is None and hasattr(request, cache_key):
        return getattr(request, cache_key)
    if limit is not None:
        entries = fetch_notifications_for_user(user, limit=limit)
        history_ids = [entry.history.id for entry in entries if entry.history is not None]
        seen_ids = get_seen_notification_ids(request, history_ids=history_ids)
        unread_count = 0
        for entry in entries:
            if entry.history is not None:
                if entry.history.id not in seen_ids:
                    unread_count += 1
            elif entry.user_notification is not None and not entry.user_notification.is_viewed:
                unread_count += 1
        return unread_count

    history_queryset = notification_queryset_for_user(user).order_by()
    seen_history_ids = HistoryNotificationSeen.objects.filter(user=user).values("history_id")
    history_unread = history_queryset.exclude(pk__in=seen_history_ids).count()
    user_unread = UserNotification.objects.filter(user=user, viewed_at__isnull=True).count()
    unread_count = history_unread + user_unread
    setattr(request, cache_key, unread_count)
    return unread_count


def _format_user_display(user) -> str:
    if not user:
        return "Système"
    if hasattr(user, "get_full_name"):
        full_name = user.get_full_name()
        if full_name:
            return full_name
    if hasattr(user, "get_username"):
        return user.get_username()
    return str(user)


def create_user_notification(
    user,
    *,
    title: str,
    message: str = "",
    level: str = UserNotification.LEVEL_INFO,
    dat=None,
    target_url: str = "",
    created_by=None,
    created_by_display: str = "",
    extra_data: dict | None = None,
) -> UserNotification | None:
    if not getattr(user, "is_authenticated", False):
        return None
    resolved_display = created_by_display or _format_user_display(created_by)
    notification_type, _ = NotificationType.objects.get_or_create(
        title=title,
        level=level or UserNotification.LEVEL_INFO,
    )
    message_content = message if message is not None else ""
    notification_message, _ = NotificationMessage.objects.get_or_create(
        content=message_content,
    )
    notification = UserNotification.objects.create(
        user=user,
        notification_type=notification_type,
        notification_message=notification_message,
        dat=dat,
        target_url=target_url,
        created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
        created_by_display=resolved_display,
        extra_data=extra_data or None,
    )
    try:
        from cintafactory.notifications.external import (
            build_event_from_user_notification,
            dispatch_external_notification,
        )

        event = build_event_from_user_notification(notification)
        dispatch_external_notification(event)
    except Exception:
        logger.exception("Failed to dispatch external notifications.")
    return notification


def mark_user_notifications_as_viewed(user, notification_ids: Sequence[int]) -> None:
    if not getattr(user, "is_authenticated", False):
        return
    if not notification_ids:
        return
    now = timezone.now()
    (
        UserNotification.objects.filter(user=user, viewed_at__isnull=True, pk__in=notification_ids)
        .update(viewed_at=now)
    )


def mark_all_notifications_as_seen(user) -> None:
    if not getattr(user, "is_authenticated", False):
        return
    history_ids = notification_queryset_for_user(user).values_list("pk", flat=True)
    batch_size = 1000
    to_create = []
    for history_id in history_ids.iterator():
        to_create.append(HistoryNotificationSeen(user=user, history_id=history_id))
        if len(to_create) >= batch_size:
            HistoryNotificationSeen.objects.bulk_create(
                to_create,
                ignore_conflicts=True,
                batch_size=batch_size,
            )
            to_create = []
    if to_create:
        HistoryNotificationSeen.objects.bulk_create(
            to_create,
            ignore_conflicts=True,
            batch_size=batch_size,
        )
    UserNotification.objects.filter(user=user, viewed_at__isnull=True).update(
        viewed_at=timezone.now(),
    )
