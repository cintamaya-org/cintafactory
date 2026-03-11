from __future__ import annotations

import os

from django.conf import settings
from django.core.checks import Error, Tags, register


_INSECURE_DJANGO_KEYS = {
    "",
    "insecure-only-for-ci",
    "insecure-test-only",
    "insecure-demo-only",
    "django-insecure-m3*wk1omhr%_7ky#c^s9i6&q@f$19+y&1-lh^1b)+tm$hcz+s1",
}

_INSECURE_LIKEC4_TOKENS = {
    "",
    "dev_token_idHaf",
    "dev_likec4_api_token_change_me",
    "replace-me",
    "replace-with-a-strong-secret",
}


@register(Tags.security)
def check_runtime_secrets(app_configs=None, **_kwargs):
    """
    Fail fast in non-debug runtimes when sensitive tokens are unset or default.
    """
    if getattr(settings, "DEBUG", False):
        return []

    enforce = os.getenv("DJANGO_ENFORCE_STRICT_SECRETS", "0").lower() in {"1", "true", "yes", "on"}
    if not enforce:
        return []

    errors: list[Error] = []
    secret_key = str(getattr(settings, "SECRET_KEY", "") or "").strip()
    if secret_key in _INSECURE_DJANGO_KEYS:
        errors.append(
            Error(
                "DJANGO_SECRET_KEY must be set to a non-default value when DEBUG is disabled.",
                id="cintafactory.E001",
            )
        )

    metadata_token = str(getattr(settings, "LIKEC4_METADATA_TOKEN", "") or "").strip()
    if metadata_token in _INSECURE_LIKEC4_TOKENS:
        errors.append(
            Error(
                "LIKEC4_METADATA_TOKEN must be set to a non-default value when DEBUG is disabled.",
                id="cintafactory.E002",
            )
        )

    api_token = str(getattr(settings, "LIKEC4_API_TOKEN", "") or "").strip()
    if api_token in _INSECURE_LIKEC4_TOKENS:
        errors.append(
            Error(
                "LIKEC4_API_TOKEN must be set to a non-default value when DEBUG is disabled.",
                id="cintafactory.E003",
            )
        )

    return errors


@register(Tags.security)
def check_runtime_http_security(app_configs=None, **_kwargs):
    if getattr(settings, "DEBUG", False):
        return []

    enforce = os.getenv("DJANGO_ENFORCE_STRICT_HTTP", "0").lower() in {"1", "true", "yes", "on"}
    if not enforce:
        return []

    errors: list[Error] = []
    allowed_hosts = {str(item).strip() for item in getattr(settings, "ALLOWED_HOSTS", []) if str(item).strip()}
    if "*" in allowed_hosts:
        errors.append(
            Error(
                "ALLOWED_HOSTS cannot contain '*' when strict HTTP security is enabled.",
                id="cintafactory.E004",
            )
        )

    if not getattr(settings, "SESSION_COOKIE_SECURE", False):
        errors.append(
            Error(
                "SESSION_COOKIE_SECURE must be enabled when strict HTTP security is enabled.",
                id="cintafactory.E005",
            )
        )

    if not getattr(settings, "CSRF_COOKIE_SECURE", False):
        errors.append(
            Error(
                "CSRF_COOKIE_SECURE must be enabled when strict HTTP security is enabled.",
                id="cintafactory.E006",
            )
        )

    csrf_origins = getattr(settings, "CSRF_TRUSTED_ORIGINS", [])
    if any(str(origin).startswith("http://") for origin in csrf_origins):
        errors.append(
            Error(
                "CSRF_TRUSTED_ORIGINS entries must use https:// when strict HTTP security is enabled.",
                id="cintafactory.E007",
            )
        )

    return errors
