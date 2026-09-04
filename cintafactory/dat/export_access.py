from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    DAT,
    DATExportAccessApproval,
    DATExportAccessEventType,
    DATExportAccessHistory,
    DATExportAccessRequest,
    DATExportAccessRequestStatus,
)
from .utils import format_user_display

PENDING_WINDOW = timedelta(minutes=5)
ACCESS_WINDOW = timedelta(hours=1)
REQUIRED_APPROVALS = 2


class ExportAccessError(Exception):
    pass


class ExportAccessPermissionDenied(ExportAccessError):
    pass


class ExportAccessConflict(ExportAccessError):
    pass


@dataclass
class ExportAccessState:
    enabled: bool
    active_request: DATExportAccessRequest | None
    approval_count: int
    approvers: list
    is_pending: bool
    is_approved: bool
    user_is_explicit_admin: bool
    user_has_approved: bool
    user_can_request: bool
    user_can_approve: bool
    user_can_download: bool
    remaining_seconds: int


def _is_explicit_dat_admin(dat: DAT, user) -> bool:
    if dat is None or user is None or not getattr(user, "is_authenticated", False):
        return False
    user_id = getattr(user, "id", None)
    if user_id is None:
        return False
    return dat.dat_admins.filter(user_id=user_id).exists()


def _log_event(
    *,
    dat: DAT,
    request: DATExportAccessRequest | None,
    event_type: str,
    actor=None,
    details: dict | None = None,
) -> DATExportAccessHistory:
    return DATExportAccessHistory.objects.create(
        dat=dat,
        request=request,
        event_type=event_type,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        details=details or {},
    )


def _expire_if_needed(active_request: DATExportAccessRequest | None) -> DATExportAccessRequest | None:
    if active_request is None:
        return None
    now = timezone.now()
    if active_request.status == DATExportAccessRequestStatus.PENDING and active_request.approve_deadline_at <= now:
        active_request.status = DATExportAccessRequestStatus.EXPIRED
        active_request.save(update_fields=["status"])
        _log_event(
            dat=active_request.dat,
            request=active_request,
            event_type=DATExportAccessEventType.REQUEST_EXPIRED,
            details={"expired_at": now.isoformat()},
        )
    elif (
        active_request.status == DATExportAccessRequestStatus.APPROVED
        and active_request.access_valid_until
        and active_request.access_valid_until <= now
    ):
        active_request.status = DATExportAccessRequestStatus.EXPIRED
        active_request.save(update_fields=["status"])
        _log_event(
            dat=active_request.dat,
            request=active_request,
            event_type=DATExportAccessEventType.ACCESS_EXPIRED,
            details={"expired_at": now.isoformat()},
        )
    return active_request


def _get_latest_request(dat: DAT) -> DATExportAccessRequest | None:
    request = (
        DATExportAccessRequest.objects.filter(dat=dat)
        .order_by("-requested_at", "-id")
        .first()
    )
    return _expire_if_needed(request)


def get_access_state(dat: DAT, actor) -> ExportAccessState:
    enabled = bool(getattr(dat, "secure_export_requires_dual_admin_approval", True))
    is_explicit_admin = _is_explicit_dat_admin(dat, actor)
    if not enabled:
        return ExportAccessState(
            enabled=False,
            active_request=None,
            approval_count=0,
            approvers=[],
            is_pending=False,
            is_approved=False,
            user_is_explicit_admin=is_explicit_admin,
            user_has_approved=False,
            user_can_request=False,
            user_can_approve=False,
            user_can_download=True,
            remaining_seconds=0,
        )

    active_request = _get_latest_request(dat)
    approvals = []
    if active_request is not None:
        approvals = list(
            active_request.approvals.select_related("approved_by").order_by("approved_at", "id")
        )
    user_id = getattr(actor, "id", None)
    user_has_approved = any(getattr(item, "approved_by_id", None) == user_id for item in approvals)
    requester_id = getattr(active_request, "requested_by_id", None) if active_request is not None else None
    user_is_requester = bool(requester_id is not None and requester_id == user_id)
    is_pending = bool(active_request and active_request.status == DATExportAccessRequestStatus.PENDING)
    is_approved = bool(active_request and active_request.status == DATExportAccessRequestStatus.APPROVED)

    remaining_seconds = 0
    if is_pending and active_request and active_request.approve_deadline_at:
        remaining_seconds = max(0, int((active_request.approve_deadline_at - timezone.now()).total_seconds()))
    if is_approved and active_request and active_request.access_valid_until:
        remaining_seconds = max(0, int((active_request.access_valid_until - timezone.now()).total_seconds()))

    user_can_request = bool(is_explicit_admin and not is_pending and not is_approved)
    user_can_approve = bool(is_explicit_admin and is_pending and not user_has_approved and not user_is_requester)
    user_can_download = bool(is_explicit_admin and is_approved and user_has_approved)
    return ExportAccessState(
        enabled=True,
        active_request=active_request,
        approval_count=len(approvals),
        approvers=approvals,
        is_pending=is_pending,
        is_approved=is_approved,
        user_is_explicit_admin=is_explicit_admin,
        user_has_approved=user_has_approved,
        user_can_request=user_can_request,
        user_can_approve=user_can_approve,
        user_can_download=user_can_download,
        remaining_seconds=remaining_seconds,
    )


@transaction.atomic
def create_request(dat: DAT, actor) -> DATExportAccessRequest:
    state = get_access_state(dat, actor)
    if not state.enabled:
        raise ExportAccessConflict("disabled")
    if not state.user_is_explicit_admin:
        raise ExportAccessPermissionDenied("not_explicit_dat_admin")
    if not state.user_can_request:
        raise ExportAccessConflict("active_request_exists")

    now = timezone.now()
    request = DATExportAccessRequest.objects.create(
        dat=dat,
        requested_by=actor if getattr(actor, "is_authenticated", False) else None,
        status=DATExportAccessRequestStatus.PENDING,
        approve_deadline_at=now + PENDING_WINDOW,
        required_approvals=REQUIRED_APPROVALS,
    )
    if getattr(actor, "is_authenticated", False):
        DATExportAccessApproval.objects.create(
            request=request,
            dat=dat,
            approved_by=actor,
        )
        _log_event(
            dat=dat,
            request=request,
            event_type=DATExportAccessEventType.APPROVED,
            actor=actor,
            details={
                "approved_by": format_user_display(actor),
                "auto": True,
            },
        )
    _log_event(
        dat=dat,
        request=request,
        event_type=DATExportAccessEventType.REQUEST_CREATED,
        actor=actor,
        details={
            "requested_by": format_user_display(actor),
            "approve_deadline_at": request.approve_deadline_at.isoformat(),
            "required_approvals": REQUIRED_APPROVALS,
        },
    )
    return request


@transaction.atomic
def approve_request(dat: DAT, actor) -> DATExportAccessRequest:
    state = get_access_state(dat, actor)
    if not state.enabled:
        raise ExportAccessConflict("disabled")
    if not state.user_is_explicit_admin:
        raise ExportAccessPermissionDenied("not_explicit_dat_admin")
    request = state.active_request
    if request is None or request.status != DATExportAccessRequestStatus.PENDING:
        raise ExportAccessConflict("no_pending_request")
    actor_id = getattr(actor, "id", None)
    if actor_id is not None and request.requested_by_id == actor_id:
        raise ExportAccessPermissionDenied("requester_cannot_self_approve")

    if not state.user_has_approved:
        DATExportAccessApproval.objects.create(
            request=request,
            dat=dat,
            approved_by=actor if getattr(actor, "is_authenticated", False) else None,
        )
        _log_event(
            dat=dat,
            request=request,
            event_type=DATExportAccessEventType.APPROVED,
            actor=actor,
            details={
                "approved_by": format_user_display(actor),
            },
        )
    approvals_count = request.approvals.count()
    if approvals_count >= request.required_approvals:
        now = timezone.now()
        request.status = DATExportAccessRequestStatus.APPROVED
        request.approved_at = now
        request.access_valid_until = now + ACCESS_WINDOW
        request.save(update_fields=["status", "approved_at", "access_valid_until"])
        _log_event(
            dat=dat,
            request=request,
            event_type=DATExportAccessEventType.ACCESS_GRANTED,
            actor=actor,
            details={
                "required_approvals": request.required_approvals,
                "access_valid_until": request.access_valid_until.isoformat() if request.access_valid_until else None,
            },
        )
    return request


def can_download(dat: DAT, actor, export_format: str) -> bool:
    state = get_access_state(dat, actor)
    if not state.enabled:
        return True
    return state.user_can_download


def record_download(dat: DAT, actor, export_format: str) -> None:
    state = get_access_state(dat, actor)
    if not state.enabled:
        return
    event_type = (
        DATExportAccessEventType.DOWNLOAD_PDF
        if export_format == "pdf"
        else DATExportAccessEventType.DOWNLOAD_JSON
    )
    _log_event(
        dat=dat,
        request=state.active_request,
        event_type=event_type,
        actor=actor,
        details={"format": export_format},
    )
