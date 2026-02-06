"""Notification helpers."""

from .external import (
    ExternalNotificationBackend,
    ExternalNotificationEvent,
    ExternalNotificationResult,
    dispatch_external_notification,
    get_external_notification_backends,
)
from .teams import TeamsWebhookBackend

__all__ = [
    "ExternalNotificationBackend",
    "ExternalNotificationEvent",
    "ExternalNotificationResult",
    "dispatch_external_notification",
    "get_external_notification_backends",
    "TeamsWebhookBackend",
]
