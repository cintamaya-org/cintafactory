from __future__ import annotations

import json
import logging
import secrets
from datetime import timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify

from .models import OAuthAccount
from .oauth_providers import OAuthProvider
from cintafactory.url_safety import is_http_url


logger = logging.getLogger(__name__)


class OAuthError(Exception):
    def __init__(self, message: str, *, details: Any | None = None):
        super().__init__(message)
        self.details = details


def build_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def build_authorize_url(provider: OAuthProvider, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(provider.scopes),
        "state": state,
    }
    params.update(provider.extra_authorize_params)
    return f"{provider.authorize_url}?{urlencode(params)}"


def exchange_code_for_token(provider: OAuthProvider, code: str, redirect_uri: str) -> dict[str, Any]:
    payload = {
        "code": code,
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    return _request_json(provider.token_url, data=payload)


def fetch_userinfo(provider: OAuthProvider, access_token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    return _request_json(provider.userinfo_url, headers=headers)


def resolve_oauth_user(
    provider: OAuthProvider,
    userinfo: dict[str, Any],
    token_data: dict[str, Any],
    *,
    request_user=None,
):
    mapping = provider.userinfo_mapping
    provider_user_id = _extract_value(userinfo, mapping.get("user_id")) or ""
    if not provider_user_id:
        raise OAuthError("Identifiant utilisateur manquant dans la reponse du fournisseur.")
    email = _extract_value(userinfo, mapping.get("email")) or ""
    email_verified = _extract_value(userinfo, mapping.get("email_verified"))
    first_name = _extract_value(userinfo, mapping.get("first_name")) or ""
    last_name = _extract_value(userinfo, mapping.get("last_name")) or ""
    full_name = _extract_value(userinfo, mapping.get("full_name")) or ""
    if full_name and not (first_name or last_name):
        parts = full_name.strip().split()
        if parts:
            first_name = parts[0]
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

    account = OAuthAccount.objects.select_related("user").filter(
        provider=provider.slug,
        provider_user_id=provider_user_id,
    ).first()
    if account:
        _update_account_tokens(account, token_data, userinfo, email=email)
        return account.user, account

    if request_user is not None and getattr(request_user, "is_authenticated", False):
        account = OAuthAccount.objects.create(
            user=request_user,
            provider=provider.slug,
            provider_user_id=provider_user_id,
            email=email or "",
            raw_profile=userinfo,
        )
        _update_account_tokens(account, token_data, userinfo, save=True)
        return request_user, account

    allow_email_linking = getattr(settings, "OAUTH_ALLOW_EMAIL_LINKING", True)
    if email and allow_email_linking and email_verified is not False:
        existing = (
            get_user_model()
            .objects.filter(email__iexact=email)
            .order_by("id")
            .first()
        )
        if existing:
            account = OAuthAccount.objects.create(
                user=existing,
                provider=provider.slug,
                provider_user_id=provider_user_id,
                email=email,
                raw_profile=userinfo,
            )
            _update_account_tokens(account, token_data, userinfo, save=True)
            return existing, account

    UserModel = get_user_model()
    username = _build_unique_username(UserModel, email or full_name or provider_user_id, provider.slug)
    user = UserModel.objects.create_user(
        username=username,
        email=email or "",
        first_name=first_name,
        last_name=last_name,
        password=None,
    )
    account = OAuthAccount.objects.create(
        user=user,
        provider=provider.slug,
        provider_user_id=provider_user_id,
        email=email or "",
        raw_profile=userinfo,
    )
    _update_account_tokens(account, token_data, userinfo, save=True)
    return user, account


def _request_json(url: str, *, headers: dict[str, str] | None = None, data: dict[str, Any] | None = None):
    timeout = getattr(settings, "OAUTH_HTTP_TIMEOUT", 10)
    if not is_http_url(url):
        logger.warning("OAuth URL rejected (non-http scheme): %s", url)
        raise OAuthError("URL du fournisseur OAuth invalide.", details=url)
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    request_data = None
    if data is not None:
        encoded = urlencode(data).encode("utf-8")
        request_data = encoded
        req_headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(url, data=request_data, headers=req_headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8") if hasattr(exc, "read") else ""
        logger.warning("OAuth HTTP error (%s): %s", exc.code, body or exc)
        raise OAuthError("Erreur lors de l'appel OAuth.", details=body) from exc
    except URLError as exc:
        logger.warning("OAuth URL error: %s", exc)
        raise OAuthError("Impossible de contacter le fournisseur OAuth.", details=str(exc)) from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        logger.warning("OAuth JSON error: %s", exc)
        raise OAuthError("Reponse OAuth invalide.", details=payload) from exc


def _build_unique_username(user_model, base: str, provider_slug: str) -> str:
    cleaned = slugify(base) if base else ""
    if not cleaned:
        cleaned = f"{provider_slug}-user"
    candidate = cleaned
    counter = 1
    while user_model.objects.filter(username=candidate).exists():
        counter += 1
        candidate = f"{cleaned}-{counter}"
    return candidate


def _extract_value(payload: dict[str, Any], field: str | None):
    if not field:
        return None
    value = payload.get(field)
    return value


def _update_account_tokens(
    account: OAuthAccount,
    token_data: dict[str, Any],
    profile: dict[str, Any],
    *,
    email: str | None = None,
    save: bool = True,
):
    account.access_token = token_data.get("access_token", "") or ""
    refresh_token = token_data.get("refresh_token")
    if refresh_token:
        account.refresh_token = refresh_token
    if email is not None and email != "":
        account.email = email
    account.token_type = token_data.get("token_type", "") or account.token_type
    scope = token_data.get("scope")
    if scope:
        account.scope = scope
    expires_in = token_data.get("expires_in")
    if expires_in:
        try:
            expires = timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            expires = None
        if expires is not None:
            account.token_expires_at = timezone.now() + expires
    account.raw_profile = profile or account.raw_profile
    if save:
        account.save(update_fields=[
            "access_token",
            "refresh_token",
            "token_expires_at",
            "token_type",
            "scope",
            "email",
            "raw_profile",
            "updated_at",
        ])
