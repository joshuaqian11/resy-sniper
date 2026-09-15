#!/usr/bin/env python3
"""EC2 entry point: read target from SSM, run snipe with Playwright, stop instance."""
import asyncio
import logging
import boto3
import urllib.request
from datetime import datetime, timezone
from database import Database
from resy import ResyClient
from snipe import run_snipe

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

SSM_PARAM_NAME = "/resy-bot/pending-target-id"
REGION = "us-east-1"


def get_instance_id() -> str:
    """Fetch this instance's ID from EC2 metadata (IMDSv2)."""
    try:
        token_req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
        )
        with urllib.request.urlopen(token_req, timeout=2) as r:
            token = r.read().decode()
        req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.read().decode()
    except Exception:
        return ""


async def main():
    ssm = boto3.client("ssm", region_name=REGION)

    # Read target ID from SSM
    try:
        resp = ssm.get_parameter(Name=SSM_PARAM_NAME)
        target_id = resp["Parameter"]["Value"]
    except Exception as e:
        logger.error(f"Failed to read target ID from SSM: {e}")
        return

    logger.info(f"Snipe runner started for target {target_id}")

    db = Database(region=REGION)
    target = db.get_target(target_id)

    if not target:
        logger.error(f"Target {target_id} not found in DynamoDB")
        return

    if target["status"] != "pending":
        logger.info(f"Target {target_id} status is {target['status']}, skipping")
        return

    config = db.get_all_config()
    resy_client = ResyClient(
        api_key=config.get("resy_api_key", ""),
        auth_token=config.get("resy_auth_token", ""),
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

        # Wait until opening time
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

    updated = db.get_target(target_id)
    status = updated["status"] if updated else "unknown"
    logger.info(f"Snipe complete — status: {status}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # Stop this EC2 instance
        instance_id = get_instance_id()
        if instance_id:
            logger.info(f"Stopping instance {instance_id}")
            ec2 = boto3.client("ec2", region_name=REGION)
            ec2.stop_instances(InstanceIds=[instance_id])
        else:
            logger.warning("Could not determine instance ID — instance will not auto-stop")
