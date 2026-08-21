class WorkflowError(Exception):
    """Base workflow subsystem error."""


class WorkflowConfigurationError(WorkflowError):
    """Workflow definition or adapter is missing or invalid."""


class WorkflowTransitionUnavailable(WorkflowError):
    """Event cannot transition current workflow state."""


class WorkflowPermissionDenied(WorkflowError):
    """Actor is not authorized for requested workflow event."""

