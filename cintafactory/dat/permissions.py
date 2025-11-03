from __future__ import annotations

from django.db.models import Q, QuerySet


def user_is_dat_admin(user) -> bool:
    """
    Determine whether the given user should bypass DAT visibility restrictions.
    """
    if user is None:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    is_role = getattr(user, "is_role", None)
    if callable(is_role):
        try:
            if is_role("admin"):
                return True
        except Exception:
            pass
    return False


def filter_dat_queryset_for_user(queryset: QuerySet, user) -> QuerySet:
    """
    Restrict a DAT queryset so that non-administrative users only see assigned items.
    """
    if user_is_dat_admin(user):
        return queryset
    if user is None or not getattr(user, "is_authenticated", False):
        return queryset.none()
    model = queryset.model
    owner_field = None
    if model is not None:
        try:
            owner_field = model._meta.get_field("owner")
        except Exception:
            owner_field = None
    if owner_field is None:
        # Fallback to prevent leaking data if schema is unexpected
        return queryset.none()
    return queryset.filter(
        Q(owner=user) | Q(participants__user=user)
    ).distinct()
