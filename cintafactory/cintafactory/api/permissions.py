from __future__ import annotations

from collections.abc import Iterable

from rest_framework.permissions import DjangoModelPermissions


class GranularModelPermissions(DjangoModelPermissions):
    """Support per-view or per-action permission overrides with model perms fallback."""

    def _normalize_required(self, required: object) -> tuple[str, ...] | None:
        if required is None:
            return None
        if isinstance(required, str):
            return (required,)
        if isinstance(required, Iterable):
            return tuple(required)
        return None

    def _get_view_required(self, view: object) -> tuple[str, ...] | None:
        mapping = getattr(view, "permission_required_by_action", None)
        action = getattr(view, "action", None)
        if mapping and action in mapping:
            return self._normalize_required(mapping[action])
        required = getattr(view, "permission_required", None)
        return self._normalize_required(required)

    def has_permission(self, request, view) -> bool:
        required = self._get_view_required(view)
        if required is not None:
            user = request.user
            return bool(user and user.is_authenticated and user.has_perms(required))
        try:
            return super().has_permission(request, view)
        except AssertionError:
            user = request.user
            return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        required = self._get_view_required(view)
        if required is not None:
            user = request.user
            return bool(user and user.is_authenticated and user.has_perms(required, obj))
        return super().has_object_permission(request, view, obj)
