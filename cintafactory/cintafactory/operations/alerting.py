from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import connection
from django.utils import timezone

from .health import collect_readiness
from ..models import AsyncJob
from .observability import iter_counters


@dataclass(frozen=True)
class AlertEvent:
    code: str
    severity: str
    summary: str
    route: str
    runbook: str
    details: dict[str, Any]


def _counter_sum(name: str, **required_labels: str) -> float:
    total = 0.0
    for metric_name, labels, value in iter_counters():
        if metric_name != name:
            continue
        if any(str(labels.get(key, "")) != str(expected) for key, expected in required_labels.items()):
            continue
        total += float(value)
    return total


def _route_for(severity: str) -> str:
    if severity == "critical":
        return str(getattr(settings, "ALERT_ROUTE_CRITICAL", "pagerduty:oncall"))
    return str(getattr(settings, "ALERT_ROUTE_WARNING", "slack:ops"))


def _runbook_link(anchor: str) -> str:
    return f"params_dev/PLAN5_ALERTING_RUNBOOK.md#{anchor}"


def _severity(value: float, *, warning: float, critical: float) -> str | None:
    if value >= critical:
        return "critical"
    if value >= warning:
        return "warning"
    return None


def _db_saturation_ratio() -> float | None:
    if connection.vendor != "postgresql":
        return None
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*)::float FROM pg_stat_activity")
            active = float((cursor.fetchone() or [0])[0] or 0.0)
            cursor.execute("SELECT current_setting('max_connections')::float")
            max_connections = float((cursor.fetchone() or [0])[0] or 0.0)
        if max_connections <= 0:
            return None
        return active / max_connections
    except Exception:
        return None


def _evaluate_export_queue_alerts(now) -> list[AlertEvent]:
    warning_seconds = int(getattr(settings, "ALERT_EXPORT_QUEUE_OLDEST_WARNING_SECONDS", 600))
    critical_seconds = int(getattr(settings, "ALERT_EXPORT_QUEUE_OLDEST_CRITICAL_SECONDS", 1200))
    queued = list(
        AsyncJob.objects.filter(status=AsyncJob.Status.QUEUED, job_type__startswith="exports.")
        .values("id", "created_at")
        .order_by("created_at")
    )
    if not queued:
        return []
    oldest_created_at = queued[0]["created_at"]
    age_seconds = max(0.0, (now - oldest_created_at).total_seconds())
    severity = _severity(age_seconds, warning=float(warning_seconds), critical=float(critical_seconds))
    if not severity:
        return []
    return [
        AlertEvent(
            code="export_queue_backlog",
            severity=severity,
            summary="Export queue oldest job age breached threshold.",
            route=_route_for(severity),
            runbook=_runbook_link("export-queue-backlog"),
            details={
                "queued_exports": len(queued),
                "oldest_age_seconds": round(age_seconds, 3),
            },
        )
    ]


def _evaluate_scan_failure_alerts() -> list[AlertEvent]:
    min_samples = int(getattr(settings, "ALERT_SCAN_MIN_SAMPLES", 20))
    warning_rate = float(getattr(settings, "ALERT_SCAN_FAILURE_WARNING_RATE", 0.03))
    critical_rate = float(getattr(settings, "ALERT_SCAN_FAILURE_CRITICAL_RATE", 0.08))
    warning_timeouts = float(getattr(settings, "ALERT_SCAN_TIMEOUT_WARNING_COUNT", 3))
    critical_timeouts = float(getattr(settings, "ALERT_SCAN_TIMEOUT_CRITICAL_COUNT", 6))

    total = _counter_sum("cinta_baseline_events_total", metric="upload.clamav.scan")
    failures = _counter_sum("cinta_baseline_events_total", metric="upload.clamav.scan", success="false")
    timeouts = _counter_sum("cinta_baseline_events_total", metric="upload.clamav.scan", outcome="scanner_timeout")
    unavailable = _counter_sum("cinta_baseline_events_total", metric="upload.clamav.scan", outcome="scanner_unavailable")
    timeout_like = timeouts + unavailable
    if total < max(min_samples, 1):
        return []

    failure_rate = failures / total if total else 0.0
    severity = _severity(failure_rate, warning=warning_rate, critical=critical_rate)
    timeout_severity = _severity(timeout_like, warning=warning_timeouts, critical=critical_timeouts)
    if timeout_severity == "critical":
        severity = "critical"
    elif timeout_severity == "warning" and severity != "critical":
        severity = "warning"
    if not severity:
        return []

    return [
        AlertEvent(
            code="scan_failures_timeouts",
            severity=severity,
            summary="Upload scan failures/timeouts exceeded tuned thresholds.",
            route=_route_for(severity),
            runbook=_runbook_link("scan-failures-and-timeouts"),
            details={
                "samples": total,
                "failures": failures,
                "failure_rate": round(failure_rate, 6),
                "timeout_like_failures": timeout_like,
            },
        )
    ]


def _evaluate_db_alerts() -> list[AlertEvent]:
    ratio = _db_saturation_ratio()
    if ratio is None:
        return []
    warning = float(getattr(settings, "ALERT_DB_SATURATION_WARNING", 0.80))
    critical = float(getattr(settings, "ALERT_DB_SATURATION_CRITICAL", 0.95))
    severity = _severity(ratio, warning=warning, critical=critical)
    if not severity:
        return []
    return [
        AlertEvent(
            code="db_saturation",
            severity=severity,
            summary="Database connection saturation is above threshold.",
            route=_route_for(severity),
            runbook=_runbook_link("database-saturation"),
            details={"saturation_ratio": round(ratio, 6)},
        )
    ]


def _evaluate_seaweedfs_alerts() -> list[AlertEvent]:
    events: list[AlertEvent] = []
    warning_errors = float(getattr(settings, "ALERT_SEAWEEDFS_ERRORS_WARNING_COUNT", 5))
    critical_errors = float(getattr(settings, "ALERT_SEAWEEDFS_ERRORS_CRITICAL_COUNT", 20))
    error_count = _counter_sum("cinta_baseline_events_total", metric="storage.seaweedfs.request", success="false")
    severity = _severity(error_count, warning=warning_errors, critical=critical_errors)
    if severity:
        events.append(
            AlertEvent(
                code="seaweedfs_errors",
                severity=severity,
                summary="SeaweedFS operation errors exceeded thresholds.",
                route=_route_for(severity),
                runbook=_runbook_link("seaweedfs-errors"),
                details={"errors": error_count},
            )
        )

    readiness = collect_readiness(profile="web")
    if not readiness.get("seaweedfs", False):
        events.append(
            AlertEvent(
                code="seaweedfs_unavailable",
                severity="critical",
                summary="SeaweedFS dependency readiness check is failing.",
                route=_route_for("critical"),
                runbook=_runbook_link("seaweedfs-errors"),
                details={"dependency_ready": False},
            )
        )
    return events


def _evaluate_auth_token_alerts() -> list[AlertEvent]:
    warning_count = float(getattr(settings, "ALERT_AUTH_FAILURE_WARNING_COUNT", 20))
    critical_count = float(getattr(settings, "ALERT_AUTH_FAILURE_CRITICAL_COUNT", 50))
    failures = _counter_sum("cinta_baseline_events_total", metric="auth.token_validation", success="false")
    severity = _severity(failures, warning=warning_count, critical=critical_count)
    if not severity:
        return []
    return [
        AlertEvent(
            code="auth_token_failures",
            severity=severity,
            summary="Authentication/token validation failures exceeded thresholds.",
            route=_route_for(severity),
            runbook=_runbook_link("auth-and-token-failures"),
            details={"failures": failures},
        )
    ]


def evaluate_runtime_alerts(*, now=None) -> list[AlertEvent]:
    now = now or timezone.now()
    alerts: list[AlertEvent] = []
    alerts.extend(_evaluate_export_queue_alerts(now))
    alerts.extend(_evaluate_scan_failure_alerts())
    alerts.extend(_evaluate_db_alerts())
    alerts.extend(_evaluate_seaweedfs_alerts())
    alerts.extend(_evaluate_auth_token_alerts())
    return alerts
