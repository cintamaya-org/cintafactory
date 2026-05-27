"""Notification helpers."""

from .external import (
    ExternalNotificationBackend,
    ExternalNotificationEvent,
    ExternalNotificationResult,
    dispatch_external_notification,
    get_external_notification_backends,
)
from .email import EmailNotificationBackend
from .teams import TeamsWebhookBackend

__all__ = [
    "ExternalNotificationBackend",
    "ExternalNotificationEvent",
    "ExternalNotificationResult",
    "EmailNotificationBackend",
    "dispatch_external_notification",
    "get_external_notification_backends",
    "TeamsWebhookBackend",
]
