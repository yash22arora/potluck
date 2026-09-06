"""The web process.

Three routes for now, and that is the whole of phase 0:

    GET /healthz   is this process alive?      (never touches the database)
    GET /readyz    can it actually do its job? (database + model config)
    GET /          who am I?

Phase 1 adds the Telegram webhook, phase 2 the Swiggy OAuth callback.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from potluck import __version__
from potluck.config import get_settings
from potluck.db.session import dispose_engine, get_engine
from potluck.llm import configured_models, missing_api_keys
from potluck.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    log.info(
        "starting",
        env=settings.env,
        dry_run=settings.dry_run,
        models=configured_models(),
    )
    if settings.dry_run is False:
        log.warning("dry_run_disabled", detail="this process can spend real money")
    yield
    await dispose_engine()
    log.info("stopped")


app = FastAPI(title="Potluck", version=__version__, lifespan=lifespan)


@app.get("/")
async def root() -> dict:
    settings = get_settings()
    return {
        "app": settings.app_name,
        "version": __version__,
        "env": settings.env,
        "dry_run": settings.dry_run,
    }


@app.get("/healthz")
async def healthz() -> dict:
    """Liveness. Deliberately dependency-free: if the process is running it
    answers, so a database blip never causes the platform to kill the app."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    """Readiness. Everything the app needs in order to be useful."""
    checks: dict[str, object] = {}
    ok = True

    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report, never crash the probe
        ok = False
        checks["database"] = f"error: {type(exc).__name__}"

    missing = missing_api_keys()
    checks["models"] = configured_models()
    if missing:
        ok = False
        checks["missing_env"] = missing

    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ready" if ok else "not ready", "checks": checks},
    )
