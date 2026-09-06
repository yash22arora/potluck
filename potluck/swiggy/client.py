"""Talking to the Swiggy MCP servers.

Written against the MCP Python SDK 2.x. Three things changed from 1.x and each
one bites:

  * the transport is `streamable_http_client`, not `streamablehttp_client`
  * it yields two streams, not three
  * headers are no longer a parameter — you hand it a configured HTTP client,
    and the SDK's HTTP library is `httpx2`, a different package from `httpx`

The value this module adds beyond the transport is what happens when the token
stops working. Swiggy answers 401 (expired or invalid) or 419 (session revoked)
and, since there are no refresh tokens, the only correct response is to mark the
account as needing re-authorization and tell a human. Retrying is pointless.

There is a wrinkle: for tool calls the SDK converts a non-2xx response into a
JSON-RPC error and the HTTP status is lost on the way. So when a session fails
we ask the server directly what it thinks of the token, rather than guessing
from an error message.
"""

from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy.ext.asyncio import AsyncSession

from potluck.logging import get_logger
from potluck.swiggy import tokens
from potluck.swiggy.servers import Surface, url_for

log = get_logger(__name__)

# Per the Swiggy docs: 401 invalid/expired, 419 session revoked.
DEAD_TOKEN_STATUSES = {401, 419}

# Generous read timeout because streamable HTTP holds SSE streams open.
TIMEOUT = httpx2.Timeout(30.0, read=300.0)


def _status_in_exception_chain(exc: BaseException) -> int | None:
    """Some failures (the SSE GET stream) do raise a real HTTP error."""
    current: BaseException | None = exc
    for _ in range(10):
        if current is None:
            return None
        if isinstance(current, httpx2.HTTPStatusError):
            code = current.response.status_code
            if code in DEAD_TOKEN_STATUSES:
                return code
        current = current.__cause__ or current.__context__
    return None


async def _ask_server_about_token(url: str, access_token: str) -> int | None:
    """Open the endpoint with this token and read the status line, nothing more.

    A GET on a streamable HTTP endpoint is the read side of the stream, so it is
    safe: a bad token is refused before anything happens, and a good one leaves
    a stream we close immediately without reading.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "text/event-stream",
    }
    try:
        async with httpx2.AsyncClient(timeout=httpx2.Timeout(10.0), follow_redirects=True) as http:
            async with http.stream("GET", url, headers=headers) as response:
                return response.status_code
    except Exception as exc:  # noqa: BLE001 - diagnostic only, never the main path
        log.debug("token_status_probe_failed", error=str(exc))
        return None


@asynccontextmanager
async def raw_session(surface: Surface, access_token: str):
    """A bare MCP session. Use SwiggyClient unless you know why you shouldn't."""
    url = url_for(surface)
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx2.AsyncClient(
        headers=headers,
        timeout=TIMEOUT,
        follow_redirects=True,
    ) as http:
        async with streamable_http_client(url, http_client=http) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session


class SwiggyClient:
    """Token-aware wrapper around the three MCP surfaces.

    async with get_sessionmaker()() as db:
        client = SwiggyClient(db)
        tools = await client.list_tools(Surface.INSTAMART)
    """

    def __init__(self, db: AsyncSession, account_key: str = tokens.DEFAULT_ACCOUNT):
        self.db = db
        self.account_key = account_key

    @asynccontextmanager
    async def _session(self, surface: Surface):
        token = await tokens.get_access_token(self.db, self.account_key)
        try:
            async with raw_session(surface, token) as session:
                yield session
        except tokens.NeedsAuthorization:
            raise
        except Exception as exc:
            status = _status_in_exception_chain(exc)
            if status is None:
                # The SDK swallowed the HTTP status, so go and ask.
                probed = await _ask_server_about_token(url_for(surface), token)
                if probed in DEAD_TOKEN_STATUSES:
                    status = probed
            if status is not None:
                await tokens.mark_needs_reauth(self.db, self.account_key)
                raise tokens.NeedsAuthorization(
                    f"Swiggy returned {status}; the token is no longer usable.",
                    self.account_key,
                ) from exc
            raise

    async def list_tools(self, surface: Surface) -> list[dict[str, Any]]:
        async with self._session(surface) as session:
            result = await session.list_tools()
        return [
            {
                "name": tool.name,
                "title": tool.title or "",
                "description": (tool.description or "").strip(),
            }
            for tool in result.tools
        ]

    async def call_tool(
        self,
        surface: Surface,
        name: str,
        arguments: dict[str, Any] | None = None,
    ):
        log.info("swiggy_tool_call", surface=surface.value, tool=name)
        async with self._session(surface) as session:
            result = await session.call_tool(name, arguments or {})
        if result.is_error:
            log.warning("swiggy_tool_error", surface=surface.value, tool=name)
        return result
