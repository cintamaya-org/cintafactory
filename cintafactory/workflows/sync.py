from __future__ import annotations

import logging
from typing import Iterable, Sequence, Tuple

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .definitions import WORKFLOW_DEFINITIONS, StepPermissionDefinition, WorkflowDefinition, WorkflowStepDefinition

logger = logging.getLogger(__name__)


def _iter_expected_permissions(
    permission_def: StepPermissionDefinition,
    role_ids: Sequence[int],
    user_ids: Sequence[int],
) -> Iterable[Tuple[str, int | None, int | None]]:
    """Build normalized tuples representing future permissions."""
    for role_id in role_ids:
        yield (permission_def.permission, role_id, None)
    for user_id in user_ids:
        yield (permission_def.permission, None, user_id)


def sync_workflow_definitions(definitions: Sequence[WorkflowDefinition] | None = None) -> None:
    """Synchronise declarative workflow definitions with the database."""

    definitions = definitions or WORKFLOW_DEFINITIONS

    Workflow = apps.get_model("workflows", "Workflow")
    WorkflowStep = apps.get_model("workflows", "WorkflowStep")
    WorkflowStepPermission = apps.get_model("workflows", "WorkflowStepPermission")
    Role = apps.get_model("users", "Role")
    User = apps.get_model("users", "User")

    with transaction.atomic():
        for workflow_def in definitions:
            model = apps.get_model(workflow_def.model)
            content_type = ContentType.objects.get_for_model(model)

            workflow, _ = Workflow.objects.update_or_create(
                code=workflow_def.code,
                defaults={
                    "name": workflow_def.name,
                    "description": workflow_def.description,
                    "content_type": content_type,
                    "is_active": True,
                },
            )

            existing_steps = {
                step.key: step
                for step in workflow.steps.all().prefetch_related("permissions")
            }
            seen_step_keys: set[str] = set()

            ordered_step_defs = sorted(
                workflow_def.steps,
                key=lambda step: (step.order, step.key),
            )

            for step_def in ordered_step_defs:
                step, _ = WorkflowStep.objects.update_or_create(
                    workflow=workflow,
                    key=step_def.key,
                    defaults={
                        "name": step_def.name,
                        "description": step_def.description,
                        "order": step_def.order,
                        "state": step_def.status,
                        "is_initial": step_def.is_initial,
                    },
                )
                seen_step_keys.add(step.key)

                expected_permissions: set[Tuple[str, int | None, int | None]] = set()
                for permission_def in step_def.permissions:
                    role_slugs = set(permission_def.roles or ())
                    user_names = set(permission_def.users or ())

                    role_map = {
                        role.slug: role.id
                        for role in Role.objects.filter(slug__in=role_slugs)
                    }
                    missing_roles = role_slugs - set(role_map.keys())
                    for slug in sorted(missing_roles):
                        logger.debug(
                            "Role '%s' not found during workflow sync for step '%s'",
                            slug,
                            step.key,
                        )

                    user_map = {
                        user.username: user.id
                        for user in User.objects.filter(username__in=user_names)
                    }
                    missing_users = user_names - set(user_map.keys())
                    for username in sorted(missing_users):
                        logger.debug(
                            "User '%s' not found during workflow sync for step '%s'",
                            username,
                            step.key,
                        )

                    expected_permissions.update(
                        _iter_expected_permissions(
                            permission_def,
                            role_ids=role_map.values(),
                            user_ids=user_map.values(),
                        )
                    )

                existing_permissions = {
                    (permission.permission_type, permission.role_id, permission.user_id): permission
                    for permission in step.permissions.all()
                }

                # Remove stale permissions
                for key, permission in existing_permissions.items():
                    if key not in expected_permissions:
                        permission.delete()

                # Add missing permissions
                for permission in expected_permissions:
                    if permission not in existing_permissions:
                        WorkflowStepPermission.objects.create(
                            step=step,
                            permission_type=permission[0],
                            role_id=permission[1],
                            user_id=permission[2],
                        )

            # Delete removed steps
            for key, step in existing_steps.items():
                if key not in seen_step_keys:
                    step.delete()
