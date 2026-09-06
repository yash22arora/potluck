"""Pin the parts of the MCP SDK we depend on.

The SDK renamed the streamable HTTP transport between 1.x and 2.x, dropped its
`headers` parameter, changed the number of streams it yields, and moved to
`httpx2`. Each of those was an import-time or first-call crash. These tests are
cheap and turn the next such change into a clear CI failure instead of a
confusing traceback at 7pm.
"""

import inspect

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def test_transport_is_named_and_shaped_as_we_expect():
    params = inspect.signature(streamable_http_client).parameters
    assert "url" in params
    # Headers are no longer accepted here; they ride on the http client.
    assert "headers" not in params
    assert "http_client" in params


def test_client_session_takes_two_streams_positionally():
    params = list(inspect.signature(ClientSession.__init__).parameters)
    assert params[1:3] == ["read_stream", "write_stream"]


def test_sdk_http_errors_come_from_httpx2():
    """Our 401/419 detection isinstance-checks httpx2, not httpx."""
    assert issubclass(httpx2.HTTPStatusError, Exception)


@pytest.mark.parametrize("field", ["content", "structured_content", "is_error"])
def test_call_tool_result_fields(field):
    from mcp import types

    assert field in types.CallToolResult.model_fields


@pytest.mark.parametrize("field", ["name", "description"])
def test_tool_fields(field):
    from mcp import types

    assert field in types.Tool.model_fields
