import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from typing import Optional
from auth import require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/targets", tags=["targets"])


class TargetCreate(BaseModel):
    venue_id: str
    venue_name: str
    date: str
    party_size: int
    opening_time: str
    preferred_time: Optional[str] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None


def _opening_time_to_cron(opening_time: datetime) -> str:
    """Convert a UTC datetime to an EventBridge cron expression, 2 min before."""
    t = opening_time.astimezone(timezone.utc) - timedelta(minutes=2)
    return f"cron({t.minute} {t.hour} {t.day} {t.month} ? {t.year})"


@router.get("", dependencies=[Depends(require_api_key)])
async def list_targets(request: Request):
    return request.app.state.db.get_all_targets()


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_api_key)])
async def add_target(body: TargetCreate, request: Request):
    db = request.app.state.db
    aws = request.app.state.aws_client
    target_data = body.model_dump()
    target_id = db.insert_target(target_data)
    target = db.get_target(target_id)

    rule_name = f"resy-bot-target-{target_id}"
    opening_time = datetime.fromisoformat(body.opening_time)
    if opening_time.tzinfo is None:
        opening_time = opening_time.replace(tzinfo=timezone.utc)
    cron_expr = _opening_time_to_cron(opening_time)
    try:
        aws.create_start_rule(rule_name, cron_expr, target_id)
    except Exception as e:
        logger.warning(f"EventBridge rule creation failed: {e}")

    return target


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_api_key)])
async def delete_target(target_id: str, request: Request):
    db = request.app.state.db
    aws = request.app.state.aws_client
    deleted = db.delete_target_if_pending(target_id)
    if not deleted:
        raise HTTPException(status_code=409, detail="Target is not pending and cannot be deleted")
    try:
        aws.delete_rule(f"resy-bot-target-{target_id}")
    except Exception as e:
        logger.warning(f"EventBridge rule deletion failed: {e}")
