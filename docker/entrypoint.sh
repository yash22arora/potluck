#!/usr/bin/env sh
# The "one image, three commands" switch.
#
#   web      run migrations, then serve
#   worker   run the scheduler
#   migrate  run migrations and exit (useful as a Railway pre-deploy step)
#
# Anything else is executed verbatim, so `docker compose run api bash` works.
set -e

case "$1" in
  web)
    echo "[entrypoint] applying migrations"
    alembic upgrade head
    echo "[entrypoint] starting web on :${PORT:-8000}"
    exec uvicorn potluck.main:app --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  worker)
    echo "[entrypoint] starting worker"
    exec python -m potluck.worker
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  *)
    exec "$@"
    ;;
esac
