"""Browser-facing routes for connecting a Swiggy account.

Three routes, and the flow between them:

    GET /auth/swiggy/start     → 307 to Swiggy's consent screen
    GET /auth/swiggy/callback  ← Swiggy sends the human back here with a code
    GET /auth/swiggy/status    → is there a usable token, and for how long

For local development the redirect must be `http://localhost:8000/...` — the
Swiggy allowlist is exact-match, and localhost is the one non-HTTPS exception
it permits.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from potluck.crypto import SecretKeyMissing
from potluck.db.session import get_session
from potluck.logging import get_logger
from potluck.swiggy import tokens

log = get_logger(__name__)

router = APIRouter(prefix="/auth/swiggy", tags=["swiggy-auth"])

# One alias, used by every route below.
Db = Annotated[AsyncSession, Depends(get_session)]


def _page(title: str, body: str, tone: str = "#14776a") -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><meta charset="utf-8">
<title>{title}</title>
<style>
 body{{font:16px/1.6 system-ui,sans-serif;max-width:34rem;
       margin:12vh auto;padding:0 1.5rem;color:#1a1d22}}
 h1{{font-size:1.4rem;margin:0 0 .6rem;color:{tone}}}
 code{{background:#f1f3f7;padding:.1em .35em;border-radius:4px;font-size:.9em}}
 @media(prefers-color-scheme:dark){{body{{background:#101216;color:#e8ebf0}}code{{background:#20242c}}}}
</style>
<h1>{title}</h1>{body}"""
    )


@router.get("/start")
async def start(
    db: Db,
    account: str = Query(tokens.DEFAULT_ACCOUNT, description="Which household account to link"),
) -> RedirectResponse:
    """Kick off authorization. Open this in a browser, not with curl."""
    try:
        url = await tokens.begin_authorization(db, account_key=account)
    except SecretKeyMissing as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("authorization_start_failed")
        raise HTTPException(
            status_code=502, detail=f"Could not start authorization: {exc}"
        ) from exc
    return RedirectResponse(url, status_code=307)


@router.get("/callback", response_class=HTMLResponse)
async def callback(
    db: Db,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> HTMLResponse:
    """Where Swiggy sends the human back. The code is single-use and lives
    120 seconds, so it is exchanged here and now."""
    if error:
        log.warning("authorization_denied", error=error, description=error_description)
        return _page(
            "Not connected",
            f"<p>Swiggy returned <code>{error}</code>."
            f"{f' {error_description}' if error_description else ''}</p>"
            "<p>You can close this tab and try again.</p>",
            tone="#b02a47",
        )

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state.")

    try:
        row = await tokens.complete_authorization(db, state=state, code=code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("authorization_completion_failed")
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {exc}") from exc

    return _page(
        "Swiggy connected",
        f"<p>Potluck can now reach Food, Instamart and Dineout as "
        f"<code>{row.account_key}</code>.</p>"
        f"<p>This access expires on "
        f"<strong>{row.expires_at:%d %b %Y, %H:%M} UTC</strong>. Swiggy does not issue "
        f"refresh tokens, so you will need to visit this page again after that.</p>"
        "<p>You can close this tab.</p>",
    )


@router.get("/status")
async def auth_status(
    db: Db,
    account: str = Query(tokens.DEFAULT_ACCOUNT),
) -> dict:
    return await tokens.status(db, account_key=account)
