# One image, three commands: web, worker, migrate.
# See docker/entrypoint.sh — that is what makes the split possible without a
# second Dockerfile drifting out of sync with this one.

# ---------- builder ---------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies before source, so editing a .py file does not reinstall the
# whole dependency tree on every build.
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project

COPY README.md alembic.ini ./
COPY potluck ./potluck
COPY alembic ./alembic
RUN --mount=type=cache,target=/root/.cache/uv uv sync --no-dev

# ---------- runtime ---------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --system potluck \
 && useradd --system --gid potluck --home-dir /app potluck

WORKDIR /app
COPY --from=builder --chown=potluck:potluck /app /app
COPY --chown=potluck:potluck docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER potluck
EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["web"]
