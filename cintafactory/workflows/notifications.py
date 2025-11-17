from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Sequence, Set

from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.utils import timezone

from dat.models import DATHistory
from .models import UserNotification


DEFAULT_NOTIFICATION_LIMIT = 99
SESSION_SEEN_KEY = "workflow_seen_notification_ids"


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


def _get_session(request: HttpRequest | None):
    if request is None:
        return None
    return getattr(request, "session", None)


def get_seen_notification_ids(request: HttpRequest | None) -> Set[int]:
    session = _get_session(request)
    if not session:
        return set()
    raw_ids = session.get(SESSION_SEEN_KEY, [])
    seen_ids: Set[int] = set()
    for value in raw_ids:
        try:
            seen_ids.add(int(value))
        except (TypeError, ValueError):
            continue
    return seen_ids


def mark_notifications_as_seen(request: HttpRequest | None, notification_ids: Iterable[int]) -> None:
    session = _get_session(request)
    if not session:
        return
    seen_ids = get_seen_notification_ids(request)
    updated = False
    for notification_id in notification_ids:
        try:
            notification_id = int(notification_id)
        except (TypeError, ValueError):
            continue
        if notification_id in seen_ids:
            continue
        seen_ids.add(notification_id)
        updated = True
    if updated:
        session[SESSION_SEEN_KEY] = list(seen_ids)
        session.modified = True


def notification_queryset_for_user(user) -> QuerySet[DATHistory]:
    if not getattr(user, "is_authenticated", False):
        return DATHistory.objects.none()
    return (
        DATHistory.objects.filter(
            Q(dat__owner=user) | Q(dat__participants__user=user),
        )
        .order_by("-performed_at", "-id")
        .distinct()
    )


def user_notification_queryset(user) -> QuerySet[UserNotification]:
    if not getattr(user, "is_authenticated", False):
        return UserNotification.objects.none()
    return UserNotification.objects.filter(user=user).order_by("-created_at", "-pk")


def fetch_notifications_for_user(
    user,
    *,
    limit: int = DEFAULT_NOTIFICATION_LIMIT,
    with_related: bool = False,
) -> List[NotificationEntry]:
    queryset = notification_queryset_for_user(user)
    if with_related:
        queryset = queryset.select_related("dat", "dat__application", "performed_by")
    history_entries = list(queryset[:limit])
    user_queryset = user_notification_queryset(user)
    if with_related:
        user_queryset = user_queryset.select_related("dat", "dat__application", "created_by")
    user_entries = list(user_queryset[:limit])
    combined = [
        NotificationEntry(source="history", history=entry)
        for entry in history_entries
    ]
    combined.extend(
        NotificationEntry(source="user", user_notification=entry)
        for entry in user_entries
    )
    def _sort_key(entry: NotificationEntry):
        identifier = 0
        if entry.history is not None:
            identifier = entry.history.id
        elif entry.user_notification is not None:
            identifier = entry.user_notification.id
        return (entry.created_at or timezone.now(), identifier)

    combined.sort(key=_sort_key, reverse=True)
    if limit:
        combined = combined[:limit]
    return combined


def get_unread_notification_count(request: HttpRequest | None, *, limit: int = DEFAULT_NOTIFICATION_LIMIT) -> int:
    user = getattr(request, "user", None)
    queryset = notification_queryset_for_user(user)
    latest_ids = list(queryset.values_list("id", flat=True)[:limit])
    if not latest_ids:
        history_unread = 0
    else:
        seen_ids = get_seen_notification_ids(request)
        history_unread = sum(1 for notification_id in latest_ids if notification_id not in seen_ids)
    user_unread = 0
    if getattr(user, "is_authenticated", False):
        user_unread = user_notification_queryset(user).filter(viewed_at__isnull=True).count()
    return history_unread + user_unread


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
    notification = UserNotification.objects.create(
        user=user,
        title=title,
        message=message,
        level=level,
        dat=dat,
        target_url=target_url,
        created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
        created_by_display=resolved_display,
        extra_data=extra_data or None,
    )
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
