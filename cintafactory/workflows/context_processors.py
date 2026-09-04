from __future__ import annotations

from .notifications import get_unread_notification_count


def workflow_notifications(request):
    """
    Provide workflow notification metadata to templates.
    """
    unread_count = get_unread_notification_count(request)
    return {
        "workflow_unread_notification_count": unread_count,
    }
