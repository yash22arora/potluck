"""Model access, kept behind one function.

Two roles, and they are deliberately separate:

  planner  the model that reads the conversation and decides what to propose.
           Quality matters; it runs a handful of times a day.
  gate     the relevance classifier from phase 5. It sees *every* message in
           the group, so it must be cheap and fast. Quality matters less than
           recall.

Because both are "provider:model" strings from the environment, the two roles
can come from different vendors, and switching either is an env var rather
than a code change.
"""

from functools import lru_cache
from typing import Literal

from langchain.chat_models import init_chat_model

from potluck.config import get_settings

Role = Literal["planner", "gate"]


@lru_cache
def get_chat_model(role: Role = "planner", temperature: float = 0.0):
    settings = get_settings()
    spec = settings.planner_model if role == "planner" else settings.gate_model
    return init_chat_model(spec, temperature=temperature)


def configured_models() -> dict[str, str]:
    """What /readyz reports, so a misconfigured deploy is obvious."""
    settings = get_settings()
    return {"planner": settings.planner_model, "gate": settings.gate_model}


def missing_api_keys() -> list[str]:
    """Which providers are referenced by the model settings but have no key."""
    settings = get_settings()
    specs = f"{settings.planner_model} {settings.gate_model}"
    missing = []
    if "anthropic" in specs and not settings.anthropic_api_key:
        missing.append("ANTHROPIC_API_KEY")
    if "openai" in specs and not settings.openai_api_key:
        missing.append("OPENAI_API_KEY")
    return missing
