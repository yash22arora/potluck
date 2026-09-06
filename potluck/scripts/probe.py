"""Phase 2's "done when": talk to Swiggy with no agent anywhere in sight.

    uv run python -m potluck.scripts.probe tools
    uv run python -m potluck.scripts.probe search milk
    uv run python -m potluck.scripts.probe addresses

If there is no usable token it prints the URL to open and stops. That is the
whole shape of this project's auth story: a program cannot fix an expired
token, only a human with a browser can.
"""

import asyncio
import json
import sys

from potluck.config import get_settings
from potluck.db.session import dispose_engine, get_sessionmaker
from potluck.logging import configure_logging
from potluck.swiggy import tokens
from potluck.swiggy.client import SwiggyClient
from potluck.swiggy.servers import Surface, all_urls

USAGE = """usage: python -m potluck.scripts.probe <command> [args]

  tools [food|instamart|dineout]   list the tools a surface exposes
  addresses                        call get_addresses (Instamart)
  search <query>                   call search_products (Instamart)
  status                           show token state without calling Swiggy
"""


def _authorize_hint(account: str) -> str:
    base = get_settings().swiggy_redirect_uri.rsplit("/auth/", 1)[0]
    return f"{base}/auth/swiggy/start?account={account}"


def _render(result) -> str:
    """Render a CallToolResult.

    MCP 2.x gives us `structured_content` when the tool declares an output
    schema, and falls back to text content blocks otherwise. Prefer the
    structured form — it is the same data without a JSON round trip.
    """
    if getattr(result, "is_error", False):
        prefix = "  tool reported an error:\n"
    else:
        prefix = ""

    structured = getattr(result, "structured_content", None)
    if structured:
        return prefix + json.dumps(structured, indent=2, default=str)[:4000]

    parts = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text is None:
            parts.append(repr(block))
            continue
        try:
            parts.append(json.dumps(json.loads(text), indent=2)[:4000])
        except (ValueError, TypeError):
            parts.append(text[:4000])
    return prefix + ("\n".join(parts) or "(empty result)")


async def run(argv: list[str]) -> int:
    configure_logging()
    if not argv:
        print(USAGE)
        return 2

    command, *rest = argv

    async with get_sessionmaker()() as db:
        if command == "status":
            print(json.dumps(await tokens.status(db), indent=2))
            print("\nsurfaces:", json.dumps(all_urls(), indent=2))
            return 0

        client = SwiggyClient(db)
        try:
            if command == "tools":
                surface = Surface(rest[0]) if rest else Surface.INSTAMART
                for tool in await client.list_tools(surface):
                    print(f"  {tool['name']:<28} {tool['description'][:70]}")
                return 0

            if command == "addresses":
                print(_render(await client.call_tool(Surface.INSTAMART, "get_addresses", {})))
                return 0

            if command == "search":
                if not rest:
                    print("search needs a query, e.g. `search milk`")
                    return 2
                result = await client.call_tool(
                    Surface.INSTAMART, "search_products", {"query": " ".join(rest)}
                )
                print(_render(result))
                return 0

            print(USAGE)
            return 2

        except tokens.NeedsAuthorization as exc:
            print(f"\n  Not authorized: {exc}")
            print("  Open this in a browser, then run the command again:\n")
            print(f"    {_authorize_hint(exc.account_key)}\n")
            return 1


def main() -> None:
    try:
        code = asyncio.run(_main())
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)


async def _main() -> int:
    try:
        return await run(sys.argv[1:])
    finally:
        await dispose_engine()


if __name__ == "__main__":
    main()
