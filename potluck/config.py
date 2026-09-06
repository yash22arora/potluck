"""Every knob in one place, every value from the environment.

Nothing else in the codebase may read os.environ directly. That rule is what
lets someone else run Potluck for their own group with nothing but a .env file.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- app ---------------------------------------------------------------
    app_name: str = "potluck"
    env: Literal["local", "staging", "prod"] = "local"
    log_level: str = "INFO"
    port: int = 8000

    # --- safety ------------------------------------------------------------
    # The master switch. While true, no tool call that spends money runs for
    # real; the Swiggy client routes to the mock instead. Default is ON so
    # that forgetting to set it can never cost you a biryani.
    dry_run: bool = True
    daily_budget_inr: int = 1500

    # --- database ----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://potluck:potluck@localhost:5432/potluck"
    db_echo: bool = False

    # --- models ------------------------------------------------------------
    # "provider:model" strings, resolved by langchain's init_chat_model.
    planner_model: str = "anthropic:claude-sonnet-4-5"
    gate_model: str = "openai:gpt-4o-mini"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # --- telegram (phase 1) ------------------------------------------------
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    public_base_url: str | None = None

    # --- security ----------------------------------------------------------
    # Used to derive the key that encrypts Swiggy tokens at rest.
    # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
    secret_key: str | None = None

    # --- swiggy mcp --------------------------------------------------------
    # The surface URLs are fixed; only the base changes (never, in practice).
    swiggy_base_url: str = "https://mcp.swiggy.com"
    swiggy_scopes: str = "mcp:tools mcp:resources mcp:prompts"
    # Must exactly match a registered redirect. http://localhost is allowed for
    # development; everything else has to be https.
    swiggy_redirect_uri: str = "http://localhost:8000/auth/swiggy/callback"

    # Development shim ONLY, read by potluck/scripts/probe.py and nothing else.
    # The agent resolves the address through the human — see "Deferred
    # requirements" in CLAUDE.md.
    swiggy_dev_address_id: str | None = None

    @property
    def swiggy_food_url(self) -> str:
        return f"{self.swiggy_base_url}/food"

    @property
    def swiggy_instamart_url(self) -> str:
        return f"{self.swiggy_base_url}/im"

    @property
    def swiggy_dineout_url(self) -> str:
        return f"{self.swiggy_base_url}/dineout"

    @property
    def is_local(self) -> bool:
        return self.env == "local"


@lru_cache
def get_settings() -> Settings:
    """Cached so the .env file is parsed once per process."""
    return Settings()
