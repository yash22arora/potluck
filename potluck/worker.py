"""The worker process.

Same image as the web process, different command. It owns everything that
happens on a clock rather than in response to a request:

    phase 6  derive patterns from Swiggy order history, nightly
    phase 7  the 17:30 nudge

Right now it schedules a heartbeat, which is enough to prove the second
container boots, reads the same config, and stays up.
"""

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from potluck.config import get_settings
from potluck.logging import configure_logging, get_logger

log = get_logger(__name__)


async def heartbeat() -> None:
    log.info("worker_heartbeat")


async def main() -> None:
    configure_logging()
    settings = get_settings()
    log.info("worker_starting", env=settings.env, dry_run=settings.dry_run)

    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(heartbeat, "interval", minutes=5, id="heartbeat")
    scheduler.start()

    # Park forever; the scheduler runs on this loop.
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
