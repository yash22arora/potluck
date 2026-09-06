"""The OAuth 2.1 protocol layer — HTTP only, no database, no FastAPI.

Swiggy's setup, and the two bits that shape everything downstream:

  * There is no client_id to copy out of a dashboard. You register a client at
    runtime (RFC 7591 dynamic client registration) and the server issues one.
    Registration is bound to an exact redirect URI, so local and deployed each
    need their own.

  * There are no refresh tokens in v1. The access token lasts five days and
    then it is simply gone. Nothing here can renew it in the background — a
    human has to walk through the browser again. Everything above this module
    is built around that fact rather than pretending otherwise.

Docs: https://mcp.swiggy.com/builders/docs/start/authenticate/
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from potluck.config import get_settings
from potluck.logging import get_logger

log = get_logger(__name__)

TIMEOUT = httpx.Timeout(20.0, connect=10.0)


@dataclass(frozen=True)
class Endpoints:
    authorization: str
    token: str
    registration: str


@dataclass(frozen=True)
class Pkce:
    verifier: str
    challenge: str
    method: str = "S256"


@dataclass(frozen=True)
class TokenResponse:
    access_token: str
    token_type: str
    expires_in: int
    scope: str | None


def _fallback_endpoints() -> Endpoints:
    """What the docs say, used if discovery is unreachable."""
    base = get_settings().swiggy_base_url.rstrip("/")
    return Endpoints(
        authorization=f"{base}/auth/authorize",
        token=f"{base}/auth/token",
        registration=f"{base}/auth/register",
    )


async def discover_endpoints(client: httpx.AsyncClient | None = None) -> Endpoints:
    """Read /.well-known/oauth-authorization-server.

    Discovery rather than hardcoding, because the whole point of the well-known
    document is that the server can move an endpoint without breaking clients.
    Falls back to the documented paths if it is unavailable.
    """
    base = get_settings().swiggy_base_url.rstrip("/")
    url = f"{base}/.well-known/oauth-authorization-server"

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT)
    try:
        response = await client.get(url)
        response.raise_for_status()
        doc = response.json()
        endpoints = Endpoints(
            authorization=doc["authorization_endpoint"],
            token=doc["token_endpoint"],
            registration=doc.get("registration_endpoint", f"{base}/auth/register"),
        )
        log.info("oauth_discovery_ok", token_endpoint=endpoints.token)
        return endpoints
    except Exception as exc:  # noqa: BLE001 - discovery is best-effort
        log.warning("oauth_discovery_failed", error=str(exc), using="documented defaults")
        return _fallback_endpoints()
    finally:
        if owns_client:
            await client.aclose()


def new_pkce() -> Pkce:
    """32 random bytes, base64url, SHA-256. Exactly what the docs specify."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return Pkce(verifier=verifier, challenge=challenge)


def new_state() -> str:
    """CSRF token tying the callback back to the request that started it."""
    return secrets.token_urlsafe(24)


async def register_client(
    endpoints: Endpoints,
    redirect_uri: str,
    client_name: str = "Potluck",
) -> tuple[str, str | None]:
    """Dynamic client registration. Returns (client_id, client_secret | None).

    A public client: PKCE is the proof of possession, so there is no secret to
    keep, and `token_endpoint_auth_method: none` says so explicitly.
    """
    settings = get_settings()
    payload = {
        "client_name": client_name,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": settings.swiggy_scopes,
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(endpoints.registration, json=payload)
        if response.status_code >= 400:
            log.error(
                "oauth_registration_failed",
                status=response.status_code,
                body=response.text[:500],
            )
            response.raise_for_status()
        doc = response.json()

    client_id = doc["client_id"]
    log.info("oauth_client_registered", client_id=client_id, redirect_uri=redirect_uri)
    return client_id, doc.get("client_secret")


def build_authorize_url(
    endpoints: Endpoints,
    client_id: str,
    redirect_uri: str,
    pkce: Pkce,
    state: str,
) -> str:
    settings = get_settings()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": pkce.challenge,
            "code_challenge_method": pkce.method,
            "state": state,
            "scope": settings.swiggy_scopes,
        }
    )
    return f"{endpoints.authorization}?{query}"


async def exchange_code(
    endpoints: Endpoints,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    client_id: str,
) -> TokenResponse:
    """Swap the authorization code for an access token.

    The code is single-use and lives 120 seconds, so this runs immediately in
    the callback handler and is never retried with the same code.

    OAuth specifies a form-encoded body; Swiggy's docs show JSON. We send the
    spec-compliant form first and fall back to JSON, rather than guessing.
    """
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            endpoints.token,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code in (400, 415, 422):
            log.info("token_exchange_retry_as_json", first_status=response.status_code)
            response = await client.post(endpoints.token, json=body)

        if response.status_code >= 400:
            log.error(
                "token_exchange_failed", status=response.status_code, body=response.text[:500]
            )
            response.raise_for_status()
        doc = response.json()

    return TokenResponse(
        access_token=doc["access_token"],
        token_type=doc.get("token_type", "Bearer"),
        expires_in=int(doc.get("expires_in", 432000)),
        scope=doc.get("scope"),
    )
