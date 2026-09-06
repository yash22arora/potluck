"""The three Swiggy MCP surfaces.

Fixed URLs, documented at
https://mcp.swiggy.com/builders/docs/start/developer/build-an-agent/

Note `/im`, not `/instamart` — an easy hour to lose.
"""

from enum import StrEnum

from potluck.config import get_settings


class Surface(StrEnum):
    FOOD = "food"
    INSTAMART = "instamart"
    DINEOUT = "dineout"


def url_for(surface: Surface) -> str:
    settings = get_settings()
    return {
        Surface.FOOD: settings.swiggy_food_url,
        Surface.INSTAMART: settings.swiggy_instamart_url,
        Surface.DINEOUT: settings.swiggy_dineout_url,
    }[surface]


def all_urls() -> dict[str, str]:
    return {surface.value: url_for(surface) for surface in Surface}
