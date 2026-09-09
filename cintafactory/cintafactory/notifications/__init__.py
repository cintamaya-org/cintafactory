# SPDX-FileCopyrightText: 2026 Cintamaya <contact@cintamaya.com>
# SPDX-FileCopyrightText: 2026 Baptiste COQUELET <github.com/BaptisteCoquelet>
# SPDX-License-Identifier: AGPL-3.0-only

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
