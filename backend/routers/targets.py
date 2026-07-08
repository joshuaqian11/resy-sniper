import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from typing import Optional
from auth import require_api_key

router = APIRouter(prefix="/api/targets", tags=["targets"])

logger = logging.getLogger(__name__)

class TargetCreate(BaseModel):
    venue_id: str
    venue_name: str
    date: str
    party_size: int
    opening_time: str
    preferred_start: Optional[str] = None
    preferred_end: Optional[str] = None

@router.get("", dependencies=[Depends(require_api_key)])
async def list_targets(request: Request):
    return await request.app.state.db.get_all_targets()

@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_api_key)])
async def add_target(body: TargetCreate, request: Request):
    db = request.app.state.db
    scheduler = request.app.state.scheduler
    aws = request.app.state.aws_client
    target_data = body.model_dump()
    target_id = await db.insert_target(target_data)
    target = await db.get_target(target_id)
    # Create EventBridge rule to start instance 10 min before opening
    rule_name = f"resy-bot-target-{target_id}"
    opening_time = datetime.fromisoformat(body.opening_time)
    if opening_time.tzinfo is None:
        opening_time = opening_time.replace(tzinfo=timezone.utc)
    prewarm_cron = _opening_time_to_cron(opening_time)
    try:
        aws.create_start_rule(rule_name, prewarm_cron, aws.instance_id)
    except Exception as e:
        logger.warning(f"EventBridge rule creation failed: {e}")
    scheduler.schedule_target(target)
    return target

@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_api_key)])
async def delete_target(target_id: int, request: Request):
    db = request.app.state.db
    scheduler = request.app.state.scheduler
    aws = request.app.state.aws_client
    deleted = await db.delete_target_if_not_booked(target_id)
    if not deleted:
        raise HTTPException(status_code=409, detail="Target is booked and cannot be deleted")
    scheduler.cancel_target(target_id)
    try:
        aws.delete_rule(f"resy-bot-target-{target_id}")
    except Exception as e:
        logger.warning(f"EventBridge rule deletion failed: {e}")

def _opening_time_to_cron(opening_time: datetime) -> str:
    """Convert opening_time to an EventBridge cron expression for 10 min before."""
    t = (opening_time - timedelta(minutes=10)).astimezone(timezone.utc)
    return f"cron({t.minute} {t.hour} {t.day} {t.month} ? {t.year})"
