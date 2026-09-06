"""Protocol-level tests. No database, no network."""

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

from potluck.config import Settings, get_settings
from potluck.swiggy import oauth
from potluck.swiggy.servers import Surface, all_urls, url_for


def test_surface_urls_are_the_documented_ones():
    urls = all_urls()
    assert urls["food"] == "https://mcp.swiggy.com/food"
    # /im, not /instamart — the easiest thing in this project to get wrong.
    assert urls["instamart"] == "https://mcp.swiggy.com/im"
    assert urls["dineout"] == "https://mcp.swiggy.com/dineout"
    assert url_for(Surface.FOOD) == urls["food"]


def test_pkce_challenge_is_s256_of_the_verifier():
    pkce = oauth.new_pkce()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(pkce.verifier.encode("ascii")).digest())
        .decode()
        .rstrip("=")
    )
    assert pkce.challenge == expected
    assert pkce.method == "S256"
    # base64url of 32 bytes, unpadded
    assert "=" not in pkce.verifier
    assert len(pkce.verifier) == 43


def test_pkce_is_not_reused():
    assert oauth.new_pkce().verifier != oauth.new_pkce().verifier
    assert oauth.new_state() != oauth.new_state()


def test_authorize_url_carries_every_required_parameter():
    endpoints = oauth._fallback_endpoints()
    pkce = oauth.new_pkce()
    url = oauth.build_authorize_url(
        endpoints,
        client_id="client-123",
        redirect_uri="http://localhost:8000/auth/swiggy/callback",
        pkce=pkce,
        state="state-abc",
    )

    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == endpoints.authorization

    query = {key: value[0] for key, value in parse_qs(parsed.query).items()}
    assert query["response_type"] == "code"
    assert query["client_id"] == "client-123"
    assert query["code_challenge"] == pkce.challenge
    assert query["code_challenge_method"] == "S256"
    assert query["state"] == "state-abc"
    assert query["redirect_uri"] == "http://localhost:8000/auth/swiggy/callback"
    assert "mcp:tools" in query["scope"]


def test_fallback_endpoints_match_the_docs():
    endpoints = oauth._fallback_endpoints()
    assert endpoints.authorization == "https://mcp.swiggy.com/auth/authorize"
    assert endpoints.token == "https://mcp.swiggy.com/auth/token"
    assert endpoints.registration == "https://mcp.swiggy.com/auth/register"


def test_localhost_redirect_is_the_default():
    """Swiggy allowlists http://localhost for development and nothing else
    non-HTTPS, so the default has to be exactly that."""
    settings = Settings(_env_file=None)
    assert settings.swiggy_redirect_uri.startswith("http://localhost:")
    assert settings.swiggy_redirect_uri.endswith("/auth/swiggy/callback")
    get_settings.cache_clear()
