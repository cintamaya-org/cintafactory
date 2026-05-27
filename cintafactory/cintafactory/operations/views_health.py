from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .health import overall_ready
from .metrics import render_prometheus_metrics


@require_GET
def health_live(_request):
    return JsonResponse({"ok": True, "status": "alive"}, status=200)


@require_GET
def health_ready(_request):
    ready, checks = overall_ready(profile="web")
    status = 200 if ready else 503
    return JsonResponse(
        {
            "ok": ready,
            "status": "ready" if ready else "not_ready",
            "checks": checks,
        },
        status=status,
    )


@require_GET
def metrics(_request):
    from django.http import HttpResponse

    return HttpResponse(
        render_prometheus_metrics(),
        content_type="text/plain; version=0.0.4; charset=utf-8",
    )
