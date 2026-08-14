"""
APScheduler-based daily runner.
Run this in a separate terminal: python scheduler.py
"""
import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import DAILY_RUN_HOUR, DAILY_RUN_MINUTE
from database import init_db
from daily_runner import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def job():
    logger.info("Scheduler triggered — running pipeline")
    try:
        result = run_pipeline()
        logger.info("Pipeline result: %s", result)
    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)


def main():
    init_db()
    scheduler = BlockingScheduler(timezone="America/New_York")
    trigger = CronTrigger(hour=DAILY_RUN_HOUR, minute=DAILY_RUN_MINUTE)
    scheduler.add_job(job, trigger, id="daily_pipeline", name="Daily Job Pipeline")

    logger.info(
        "Scheduler started. Pipeline will run daily at %02d:%02d ET. "
        "Press Ctrl+C to stop.",
        DAILY_RUN_HOUR, DAILY_RUN_MINUTE,
    )

    def _shutdown(signum, frame):
        logger.info("Shutdown signal received")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    scheduler.start()


if __name__ == "__main__":
    main()
