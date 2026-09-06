"""Persistence and orchestration for the Swiggy authorization flow.

Everything that touches the database lives here; the protocol itself is in
oauth.py. The split matters because the protocol is testable without Postgres
and the storage is testable without the network.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from potluck.config import get_settings
from potluck.crypto import decrypt, encrypt
from potluck.db.models import SwiggyAuthRequest, SwiggyOAuthClient, SwiggyToken
from potluck.logging import get_logger
from potluck.swiggy import oauth

log = get_logger(__name__)

DEFAULT_ACCOUNT = "default"
AUTH_REQUEST_TTL = timedelta(minutes=15)
# Treat a token as expired slightly early, so a call never starts with 30
# seconds of validity left and dies halfway through a checkout.
EXPIRY_SKEW = timedelta(minutes=10)


class NeedsAuthorization(RuntimeError):
    """No usable token. The only cure is a human in a browser.

    Carries the URL to send them to, so callers (the Telegram bot, the probe
    script) can surface it rather than just failing.
    """

    def __init__(self, message: str, account_key: str = DEFAULT_ACCOUNT):
        super().__init__(message)
        self.account_key = account_key


async def _get_or_register_client(
    session: AsyncSession,
    endpoints: oauth.Endpoints,
    redirect_uri: str,
) -> str:
    """Registration happens once per (issuer, redirect_uri) and is then reused."""
    issuer = get_settings().swiggy_base_url.rstrip("/")

    row = await session.scalar(
        select(SwiggyOAuthClient).where(
            SwiggyOAuthClient.issuer == issuer,
            SwiggyOAuthClient.redirect_uri == redirect_uri,
        )
    )
    if row is not None:
        return row.client_id

    client_id, client_secret = await oauth.register_client(endpoints, redirect_uri)
    session.add(
        SwiggyOAuthClient(
            issuer=issuer,
            redirect_uri=redirect_uri,
            client_id=client_id,
            client_secret_enc=encrypt(client_secret) if client_secret else None,
        )
    )
    await session.commit()
    return client_id


async def begin_authorization(
    session: AsyncSession,
    account_key: str = DEFAULT_ACCOUNT,
) -> str:
    """Start the flow. Returns the URL to send the human to."""
    settings = get_settings()
    redirect_uri = settings.swiggy_redirect_uri

    endpoints = await oauth.discover_endpoints()
    client_id = await _get_or_register_client(session, endpoints, redirect_uri)

    pkce = oauth.new_pkce()
    state = oauth.new_state()

    session.add(
        SwiggyAuthRequest(
            state=state,
            account_key=account_key,
            code_verifier_enc=encrypt(pkce.verifier),
            redirect_uri=redirect_uri,
            expires_at=datetime.now(UTC) + AUTH_REQUEST_TTL,
        )
    )
    await session.commit()

    log.info("authorization_started", account_key=account_key, state=state)
    return oauth.build_authorize_url(endpoints, client_id, redirect_uri, pkce, state)


async def complete_authorization(session: AsyncSession, state: str, code: str) -> SwiggyToken:
    """Handle the callback: validate state, exchange the code, store the token."""
    request = await session.get(SwiggyAuthRequest, state)
    if request is None:
        raise ValueError("Unknown state — this callback did not come from us.")
    if request.consumed:
        raise ValueError("This authorization was already completed.")
    if request.expires_at < datetime.now(UTC):
        raise ValueError("This authorization request expired. Start again.")

    endpoints = await oauth.discover_endpoints()
    client_id = await _get_or_register_client(session, endpoints, request.redirect_uri)

    token = await oauth.exchange_code(
        endpoints,
        code=code,
        code_verifier=decrypt(request.code_verifier_enc),
        redirect_uri=request.redirect_uri,
        client_id=client_id,
    )

    expires_at = datetime.now(UTC) + timedelta(seconds=token.expires_in)
    existing = await session.get(SwiggyToken, request.account_key)
    if existing is None:
        existing = SwiggyToken(account_key=request.account_key)
        session.add(existing)

    existing.access_token_enc = encrypt(token.access_token)
    existing.token_type = token.token_type
    existing.scope = token.scope
    existing.obtained_at = datetime.now(UTC)
    existing.expires_at = expires_at
    existing.needs_reauth = False

    request.consumed = True
    await session.commit()

    log.info(
        "authorization_completed",
        account_key=request.account_key,
        expires_at=expires_at.isoformat(),
        scope=token.scope,
    )
    return existing


async def get_access_token(
    session: AsyncSession,
    account_key: str = DEFAULT_ACCOUNT,
) -> str:
    """The token for this account, or NeedsAuthorization if there isn't a usable one."""
    row = await session.get(SwiggyToken, account_key)
    if row is None:
        raise NeedsAuthorization("No Swiggy token stored yet.", account_key)
    if row.needs_reauth:
        raise NeedsAuthorization("Swiggy rejected the stored token.", account_key)
    if row.expires_at - EXPIRY_SKEW < datetime.now(UTC):
        raise NeedsAuthorization("The Swiggy token has expired.", account_key)
    return decrypt(row.access_token_enc)


async def mark_needs_reauth(session: AsyncSession, account_key: str = DEFAULT_ACCOUNT) -> None:
    """Called when Swiggy answers 401 or 419. There is nothing to refresh."""
    row = await session.get(SwiggyToken, account_key)
    if row is not None:
        row.needs_reauth = True
        await session.commit()
        log.warning("swiggy_token_invalidated", account_key=account_key)


async def status(session: AsyncSession, account_key: str = DEFAULT_ACCOUNT) -> dict:
    """What /auth/swiggy/status reports. Never returns the token itself."""
    row = await session.get(SwiggyToken, account_key)
    if row is None:
        return {"authorized": False, "reason": "no token stored"}

    now = datetime.now(UTC)
    expired = row.expires_at <= now
    return {
        "authorized": not (expired or row.needs_reauth),
        "account_key": account_key,
        "scope": row.scope,
        "obtained_at": row.obtained_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "expires_in_hours": max(0, round((row.expires_at - now).total_seconds() / 3600, 1)),
        "needs_reauth": row.needs_reauth,
    }


async def purge_expired_auth_requests(session: AsyncSession) -> int:
    """Housekeeping for abandoned flows. The worker can call this daily."""
    result = await session.execute(
        delete(SwiggyAuthRequest).where(SwiggyAuthRequest.expires_at < datetime.now(UTC))
    )
    await session.commit()
    return result.rowcount or 0
