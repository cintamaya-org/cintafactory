# SPDX-FileCopyrightText: 2026 Cintamaya <contact@cintamaya.com>
# SPDX-FileCopyrightText: 2026 Baptiste COQUELET <github.com/BaptisteCoquelet>
# SPDX-License-Identifier: AGPL-3.0-only

class WorkflowError(Exception):
    """Base workflow subsystem error."""


class WorkflowConfigurationError(WorkflowError):
    """Workflow definition or adapter is missing or invalid."""


class WorkflowTransitionUnavailable(WorkflowError):
    """Event cannot transition current workflow state."""


class WorkflowPermissionDenied(WorkflowError):
    """Actor is not authorized for requested workflow event."""

