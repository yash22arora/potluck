"""Phase 0's only tests. They exist so CI has something true to protect.

Note what is NOT tested: /readyz needs a database, so it belongs in an
integration test once phase 1 gives us a table worth talking to.
"""

from httpx import ASGITransport, AsyncClient

from potluck.config import Settings
from potluck.main import app


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_healthz_needs_nothing():
    async with await _client() as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_root_reports_identity():
    async with await _client() as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["app"] == "potluck"


def test_dry_run_defaults_on():
    """The safety switch must default to ON. If this test ever fails,
    something has made it possible to spend money by forgetting a variable."""
    assert Settings(_env_file=None).dry_run is True
