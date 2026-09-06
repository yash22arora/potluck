"""Phase 2's "done when": talk to Swiggy with no agent anywhere in sight.

    uv run python -m potluck.scripts.probe status
    uv run python -m potluck.scripts.probe tools instamart
    uv run python -m potluck.scripts.probe schema instamart search_products
    uv run python -m potluck.scripts.probe addresses
    uv run python -m potluck.scripts.probe search milk

If there is no usable token it prints the URL to open and stops. That is the
whole shape of this project's auth story: a program cannot fix an expired
token, only a human with a browser can.

On the address: most Instamart tools need an `addressId`, and this script takes
it from SWIGGY_DEV_ADDRESS_ID. That variable is a development convenience and
nothing in the agent reads it — the agent asks a human which address, because
Swiggy's own get_addresses response declines to guess. See "Deferred
requirements" in CLAUDE.md.
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

  status                            token state, no network
  tools [surface]                   list a surface's tools
  schema <surface> <tool>           print a tool's JSON input schema
  addresses                         saved addresses, with ids you can copy
  search <query>                    search_products (needs SWIGGY_DEV_ADDRESS_ID)

  surface is one of: food, instamart, dineout   (default: instamart)
"""


def _authorize_hint(account: str) -> str:
    base = get_settings().swiggy_redirect_uri.rsplit("/auth/", 1)[0]
    return f"{base}/auth/swiggy/start?account={account}"


def _payload(result) -> dict | list | str:
    """Unwrap a CallToolResult into whatever the tool actually returned."""
    structured = getattr(result, "structured_content", None)
    if structured:
        return structured
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text is None:
            continue
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return text
    return "(empty result)"


def _render(result) -> str:
    prefix = "  tool reported an error:\n" if getattr(result, "is_error", False) else ""
    payload = _payload(result)
    if isinstance(payload, str):
        return prefix + payload[:4000]
    return prefix + json.dumps(payload, indent=2, default=str)[:4000]


def _print_addresses(payload) -> None:
    """A copyable table. Address lines are personal data, so only the tag shows."""
    if not isinstance(payload, dict):
        print(payload)
        return

    addresses = payload.get("addresses", [])
    print(f"\n  {len(addresses)} saved address(es):\n")
    for address in addresses:
        tag = address.get("addressTag") or "(untagged)"
        category = address.get("addressCategory") or "-"
        print(f"    {tag:<20} {category:<8} {address.get('id', '')}")

    resolution = payload.get("resolution") or {}
    if resolution.get("needsUserClarification"):
        print(
            "\n  Swiggy says needsUserClarification=true — it will not pick one for you,\n"
            "  and neither should the agent. For the probe, copy an id into .env:\n"
            "\n    SWIGGY_DEV_ADDRESS_ID=<id>\n"
        )


async def run(argv: list[str]) -> int:
    configure_logging()
    if not argv:
        print(USAGE)
        return 2

    command, *rest = argv
    settings = get_settings()

    async with get_sessionmaker()() as db:
        if command == "status":
            print(json.dumps(await tokens.status(db), indent=2))
            print("\nsurfaces:", json.dumps(all_urls(), indent=2))
            print("dev address id:", settings.swiggy_dev_address_id or "(unset)")
            return 0

        client = SwiggyClient(db)
        try:
            if command == "tools":
                surface = Surface(rest[0]) if rest else Surface.INSTAMART
                for tool in await client.list_tools(surface):
                    print(f"  {tool['name']:<28} {tool['description'][:70]}")
                return 0

            if command == "schema":
                if len(rest) < 2:
                    print(
                        "schema needs a surface and a tool, e.g. `schema instamart search_products`"
                    )
                    return 2
                surface = Surface(rest[0])
                wanted = rest[1]
                for tool in await client.list_tools(surface, include_schema=True):
                    if tool["name"] == wanted:
                        print(json.dumps(tool["input_schema"], indent=2))
                        return 0
                print(f"no tool named {wanted!r} on {surface.value}")
                return 1

            if command == "addresses":
                result = await client.call_tool(Surface.INSTAMART, "get_addresses", {})
                if getattr(result, "is_error", False):
                    print(_render(result))
                    return 1
                _print_addresses(_payload(result))
                return 0

            if command == "search":
                if not rest:
                    print("search needs a query, e.g. `search milk`")
                    return 2
                if not settings.swiggy_dev_address_id:
                    print(
                        "\n  search_products needs an addressId.\n"
                        "  Run `make probe c=addresses`, then put one in .env as\n"
                        "  SWIGGY_DEV_ADDRESS_ID, and restart nothing — this script "
                        "reads it fresh.\n"
                    )
                    return 2
                result = await client.call_tool(
                    Surface.INSTAMART,
                    "search_products",
                    {"query": " ".join(rest), "addressId": settings.swiggy_dev_address_id},
                )
                print(_render(result))
                return 1 if getattr(result, "is_error", False) else 0

            print(USAGE)
            return 2

        except tokens.NeedsAuthorization as exc:
            print(f"\n  Not authorized: {exc}")
            print("  Open this in a browser, then run the command again:\n")
            print(f"    {_authorize_hint(exc.account_key)}\n")
            return 1


async def _main() -> int:
    try:
        return await run(sys.argv[1:])
    finally:
        await dispose_engine()


def main() -> None:
    try:
        code = asyncio.run(_main())
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)


if __name__ == "__main__":
    main()
