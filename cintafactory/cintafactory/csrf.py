import logging

from django.views.csrf import csrf_failure as django_csrf_failure

logger = logging.getLogger("django.security.csrf")


def csrf_failure(request, reason="", template_name="403_csrf.html"):
    logger.warning(
        "csrf_rejected path=%s method=%s reason=%s has_cookie=%s has_header=%s has_form=%s",
        request.path,
        request.method,
        reason,
        bool(request.COOKIES.get("csrftoken")),
        bool(request.headers.get("X-CSRFToken")),
        bool(request.POST.get("csrfmiddlewaretoken")),
    )
    return django_csrf_failure(request, reason=reason, template_name=template_name)
