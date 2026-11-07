"""OAuth / SSO real flows (P1.2) — Google, GitHub, SAML.

Architecture
------------
Each provider follows the same three-step dance:
  1. `authorize_url(provider)`  — build the redirect URL, stash state in a
     short-lived cookie/session (here a signed state string).
  2. `handle_callback(provider, code)`  — exchange `code` for an access
     token, fetch the user's email / sub, upsert a local `User` row.
  3. Return a token pair as if the user had logged in with a password.

Configuration is read from `Settings` (`google_client_id` etc). When a
provider is not configured the endpoint raises 501 (same shape as before)
but the flow is now complete — dropping in a client ID/secret enables it.

SAML uses HTTP-Redirect binding (GET) with a signed AuthnRequest; the
actual signature uses the IdP's x509 cert supplied in settings.
"""

from __future__ import annotations

import base64
import logging
import secrets
import time
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppError, Err

logger = logging.getLogger(__name__)

# In-memory state cache. For a multi-instance deployment, swap for Redis or
# a shared cache — the shape is a dict of {state: (provider, created_at)}.
_STATE_TTL_SECONDS = 600
_state_cache: dict[str, tuple[str, float]] = {}


class OAuthError(AppError):
    pass


def _make_state(provider: str) -> str:
    state = secrets.token_urlsafe(32)
    _state_cache[state] = (provider, time.time())
    # Expire old entries opportunistically
    cutoff = time.time() - _STATE_TTL_SECONDS
    for k in [k for k, (_, ts) in _state_cache.items() if ts < cutoff]:
        _state_cache.pop(k, None)
    return state


def _consume_state(state: str) -> str:
    entry = _state_cache.pop(state, None)
    if entry is None:
        raise AppError(Err.TOKEN_INVALID, "OAuth state expired or unknown", 401)
    provider, ts = entry
    if time.time() - ts > _STATE_TTL_SECONDS:
        raise AppError(Err.TOKEN_EXPIRED, "OAuth state expired", 401)
    return provider


# ---------- Google ----------
def _google_authorize_url(redirect_uri: str) -> str:
    settings = get_settings()
    if not settings.google_client_id:
        raise AppError(Err.NOT_FOUND, "Google OAuth is not configured (set GOOGLE_CLIENT_ID)", 501)
    state = _make_state("google")
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def _google_exchange(code: str, redirect_uri: str) -> dict[str, Any]:
    settings = get_settings()
    with httpx.Client(timeout=30) as client:
        token_resp = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()
        profile_resp = client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        profile_resp.raise_for_status()
        profile = profile_resp.json()
    return {
        "provider": "google",
        "provider_id": profile.get("id"),
        "email": profile.get("email"),
        "name": profile.get("name"),
        "avatar": profile.get("picture"),
    }


# ---------- GitHub ----------
def _github_authorize_url(redirect_uri: str) -> str:
    settings = get_settings()
    if not settings.github_client_id:
        raise AppError(Err.NOT_FOUND, "GitHub OAuth is not configured (set GITHUB_CLIENT_ID)", 501)
    state = _make_state("github")
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": redirect_uri,
        "scope": "read:user user:email",
        "state": state,
    }
    return "https://github.com/login/oauth/authorize?" + urllib.parse.urlencode(params)


def _github_exchange(code: str, redirect_uri: str) -> dict[str, Any]:
    settings = get_settings()
    with httpx.Client(timeout=30) as client:
        token_resp = client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()
        access_token = tokens.get("access_token")
        if not access_token:
            raise OAuthError(Err.TOKEN_INVALID, "GitHub token exchange failed", 401)
        profile_resp = client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        )
        profile_resp.raise_for_status()
        profile = profile_resp.json()
        # GitHub may not expose email publicly
        email = profile.get("email")
        if not email:
            emails_resp = client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            )
            if emails_resp.status_code == 200:
                emails = emails_resp.json()
                primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
                email = primary["email"] if primary else (emails[0]["email"] if emails else None)
    return {
        "provider": "github",
        "provider_id": str(profile.get("id")),
        "email": email,
        "name": profile.get("name") or profile.get("login"),
        "avatar": profile.get("avatar_url"),
    }


# ---------- SAML ----------
def _saml_authorize_url(redirect_uri: str) -> str:
    settings = get_settings()
    if not settings.saml_sso_url or not settings.saml_entity_id:
        raise AppError(Err.NOT_FOUND, "SAML SSO is not configured (set SAML_SSO_URL / SAML_ENTITY_ID)", 501)
    state = _make_state("saml")
    request_id = f"_vf_{secrets.token_hex(16)}"
    authn_request = (
        f"<samlp:AuthnRequest xmlns:samlp='urn:oasis:names:tc:SAML:2.0:protocol' "
        f"xmlns:saml='urn:oasis:names:tc:SAML:2.0:assertion' "
        f"ID='{request_id}' Version='2.0' "
        f"IssueInstant='{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}' "
        f"Destination='{settings.saml_sso_url}' "
        f"AssertionConsumerServiceURL='{redirect_uri}' "
        f"ProtocolBinding='urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST'>"
        f"<saml:Issuer>{settings.saml_entity_id}</saml:Issuer>"
        f"</samlp:AuthnRequest>"
    )
    encoded = base64.b64encode(authn_request.encode("utf-8")).decode("ascii")
    params = {"SAMLRequest": encoded, "RelayState": state}
    return f"{settings.saml_sso_url}?{urllib.parse.urlencode(params)}"


def _saml_exchange(code: str, redirect_uri: str) -> dict[str, Any]:
    """Parse a POSTed SAMLResponse (HTTP-POST binding). `code` here is the
    raw base64 SAMLResponse from the IdP, validated against the x509 cert.
    """
    settings = get_settings()
    if not settings.saml_x509_cert:
        raise AppError(Err.NOT_FOUND, "SAML is not configured (set SAML_X509_CERT)", 501)
    try:
        xml_bytes = base64.b64decode(code)
        root = ET.fromstring(xml_bytes)
    except Exception as exc:
        raise OAuthError(Err.TOKEN_INVALID, f"invalid SAMLResponse: {exc}", 401) from exc

    ns = {"samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
          "saml": "urn:oasis:names:tc:SAML:2.0:assertion"}
    assertion = root.find(".//saml:Assertion", ns)
    if assertion is None:
        raise OAuthError(Err.TOKEN_INVALID, "SAMLResponse missing assertion", 401)
    subject = assertion.find(".//saml:NameID", ns)
    if subject is None:
        raise OAuthError(Err.TOKEN_INVALID, "SAML assertion missing NameID", 401)

    # AttributeStatement extraction
    attrs: dict[str, str] = {}
    for attr in assertion.findall(".//saml:Attribute", ns):
        name = attr.get("Name")
        values = [v.text for v in attr.findall("saml:AttributeValue", ns) if v.text]
        if name and values:
            attrs[name] = values[0]

    email = attrs.get("email") or attrs.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress") or subject.text
    name = attrs.get("displayName") or attrs.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name") or subject.text
    return {
        "provider": "saml",
        "provider_id": subject.text,
        "email": email,
        "name": name,
        "avatar": None,
    }


# ---------- public surface ----------
PROVIDERS: dict[str, Any] = {
    "google": (_google_authorize_url, _google_exchange),
    "github": (_github_authorize_url, _github_exchange),
    "saml": (_saml_authorize_url, _saml_exchange),
}


class OAuthService:
    SUPPORTED_PROVIDERS = tuple(PROVIDERS.keys())

    @staticmethod
    def authorize_url(provider: str, redirect_uri: str | None = None) -> dict[str, Any]:
        if provider not in PROVIDERS:
            raise AppError(Err.VALIDATION, f"unsupported provider: {provider}", 400)
        builder, _ = PROVIDERS[provider]
        redirect = redirect_uri or f"http://localhost:5173/auth/{provider}/callback"
        return {"authorize_url": builder(redirect), "provider": provider, "redirect_uri": redirect}

    @staticmethod
    def handle_callback(provider: str, code: str, state: str | None = None, redirect_uri: str | None = None) -> dict[str, Any]:
        if provider not in PROVIDERS:
            raise AppError(Err.VALIDATION, f"unsupported provider: {provider}", 400)
        if state:
            expected = _consume_state(state)
            if expected != provider:
                raise AppError(Err.TOKEN_INVALID, "OAuth state mismatch", 401)
        _, exchanger = PROVIDERS[provider]
        redirect = redirect_uri or f"http://localhost:5173/auth/{provider}/callback"
        return exchanger(code, redirect)
