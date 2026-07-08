import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from snipe import run_snipe

logger = logging.getLogger(__name__)

def _eventbridge_rule_name(target_id: int) -> str:
    return f"resy-bot-target-{target_id}"

def _opening_time_to_cron(opening_time: datetime) -> str:
    """Convert a UTC datetime to an EventBridge cron expression (UTC)."""
    t = opening_time.astimezone(timezone.utc) - timedelta(minutes=10)
    return f"cron({t.minute} {t.hour} {t.day} {t.month} ? {t.year})"

class SnipeScheduler:
    def __init__(self, db, resy_client, sms_client, aws_client):
        self.db = db
        self.resy_client = resy_client
        self.sms_client = sms_client
        self.aws_client = aws_client
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._active_jobs: set[int] = set()

    def start(self):
        self._scheduler.start()

    def shutdown(self):
        self._scheduler.shutdown(wait=False)

    def has_job(self, target_id: int) -> bool:
        return self._scheduler.get_job(str(target_id)) is not None

    def schedule_target(self, target: dict):
        target_id = target["id"]
        opening_time = datetime.fromisoformat(target["opening_time"])
        if opening_time.tzinfo is None:
            opening_time = opening_time.replace(tzinfo=timezone.utc)

        if opening_time <= datetime.now(timezone.utc):
            logger.warning(f"Target {target_id} opening_time is in the past — skipping")
            return

        # Schedule the pre-warm 5 minutes before opening time.
        # If that time is already past (e.g. target added less than 5 min before
        # opening), fire immediately — the snipe loop will still wait until the
        # exact opening_time before polling.
        prewarm_time = max(
            opening_time - timedelta(minutes=5),
            datetime.now(timezone.utc) + timedelta(seconds=1),
        )

        self._scheduler.add_job(
            self._run_prewarm_and_snipe,
            "date",
            run_date=prewarm_time,
            id=str(target_id),
            args=[target],
            misfire_grace_time=600,
        )
        logger.info(f"Scheduled snipe for target {target_id} at {opening_time.isoformat()}")

    def cancel_target(self, target_id: int):
        job = self._scheduler.get_job(str(target_id))
        if job:
            job.remove()
            logger.info(f"Cancelled snipe job for target {target_id}")

    async def _run_prewarm_and_snipe(self, target: dict):
        target_id = target["id"]
        opening_time = datetime.fromisoformat(target["opening_time"])
        if opening_time.tzinfo is None:
            opening_time = opening_time.replace(tzinfo=timezone.utc)

        self._active_jobs.add(target_id)
        try:
            # Pre-warm connection 5 minutes before opening using real target data
            logger.info(f"[{target['venue_name']}] Pre-warming connection")
            await self.resy_client.connect(
                venue_id=target["venue_id"],
                date=target["date"],
                party_size=target["party_size"],
            )

            # Wait until exact opening time
            now = datetime.now(timezone.utc)
            wait_seconds = (opening_time - now).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

            await run_snipe(target, self.resy_client, self.sms_client, self.db)
        finally:
            await self.resy_client.close()
            self._active_jobs.discard(target_id)
            if not self._active_jobs and os.environ.get("AUTO_STOP") == "true":
                logger.info("All jobs complete — stopping instance")
                self.aws_client.stop_self()

    async def reload_pending(self):
        """On startup, reschedule all pending targets from the database."""
        targets = await self.db.get_pending_targets()
        for target in targets:
            self.schedule_target(target)
        logger.info(f"Reloaded {len(targets)} pending targets from database")
