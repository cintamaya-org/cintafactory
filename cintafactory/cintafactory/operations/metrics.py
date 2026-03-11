from __future__ import annotations

from django.db.models import Count

from .health import collect_readiness
from ..models import AsyncJob
from .observability import iter_counters


def _format_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    parts = [f'{key}="{value}"' for key, value in sorted(labels.items(), key=lambda item: item[0])]
    return "{" + ",".join(parts) + "}"


def _render_counter(name: str, value: float, labels: dict[str, str]) -> str:
    return f"{name}{_format_labels(labels)} {value}"


def render_prometheus_metrics() -> str:
    lines: list[str] = []
    lines.append("# TYPE cinta_baseline_events_total counter")
    lines.append("# TYPE cinta_web_requests_total counter")
    for name, labels, value in iter_counters():
        if name not in {"cinta_baseline_events_total", "cinta_web_requests_total"}:
            continue
        lines.append(_render_counter(name, value, labels))

    lines.append("# TYPE cinta_async_jobs_status gauge")
    status_counts = AsyncJob.objects.values("status").annotate(total=Count("id")).order_by("status")
    for row in status_counts:
        lines.append(_render_counter("cinta_async_jobs_status", float(row["total"]), {"status": str(row["status"])}))

    queued = AsyncJob.objects.filter(status=AsyncJob.Status.QUEUED).count()
    running = AsyncJob.objects.filter(status=AsyncJob.Status.RUNNING).count()
    lines.append("# TYPE cinta_async_queue_backlog gauge")
    lines.append(f"cinta_async_queue_backlog {float(queued)}")
    lines.append("# TYPE cinta_async_workers_running gauge")
    lines.append(f"cinta_async_workers_running {float(running)}")

    readiness = collect_readiness(profile="web")
    lines.append("# TYPE cinta_dependency_up gauge")
    for check_name, ready in sorted(readiness.items(), key=lambda item: item[0]):
        lines.append(_render_counter("cinta_dependency_up", 1.0 if ready else 0.0, {"dependency": check_name}))

    return "\n".join(lines) + "\n"
