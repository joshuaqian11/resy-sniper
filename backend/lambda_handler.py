import asyncio
import logging
from datetime import datetime, timezone
from database import Database
from resy import ResyClient
from snipe import run_snipe

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def _run(target: dict, db: Database):
    config = db.get_all_config()
    resy_client = ResyClient(
        api_key=config.get("resy_api_key", ""),
        email=config.get("resy_email", ""),
        password=config.get("resy_password", ""),
        cookies=config.get("resy_cookies", ""),
    )
    try:
        await resy_client.connect(
            venue_id=target["venue_id"],
            date=target["date"],
            party_size=target["party_size"],
        )

        opening_time = datetime.fromisoformat(target["opening_time"])
        if opening_time.tzinfo is None:
            opening_time = opening_time.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        wait_seconds = (opening_time - now).total_seconds()
        if wait_seconds > 0:
            logger.info(f"Waiting {wait_seconds:.0f}s until opening time")
            await asyncio.sleep(wait_seconds)

        await run_snipe(target, resy_client, db)
    finally:
        await resy_client.close()


def handler(event, context):
    target_id = event.get("target_id")
    if not target_id:
        logger.error("No target_id in event")
        return {"statusCode": 400, "body": "Missing target_id"}

    db = Database()
    target = db.get_target(target_id)

    if not target:
        logger.error(f"Target {target_id} not found")
        return {"statusCode": 404, "body": "Target not found"}

    if target["status"] != "pending":
        logger.info(f"Target {target_id} status is {target['status']}, skipping")
        return {"statusCode": 200, "body": f"Skipped — status is {target['status']}"}

    logger.info(f"Starting snipe for target {target_id} ({target.get('venue_name')})")
    asyncio.run(_run(target, db))

    updated = db.get_target(target_id)
    status = updated["status"] if updated else "unknown"
    logger.info(f"Snipe complete for target {target_id} — status: {status}")
    return {"statusCode": 200, "body": f"Snipe complete — {status}"}
