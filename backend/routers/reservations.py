import logging
from fastapi import APIRouter, Depends, Request
from auth import require_api_key

router = APIRouter(prefix="/api/reservations", tags=["reservations"])
logger = logging.getLogger(__name__)

@router.get("", dependencies=[Depends(require_api_key)])
async def list_reservations(request: Request):
    resy_client = request.app.state.scheduler.resy_client
    if not resy_client.auth_token:
        return []
    try:
        return await resy_client.get_reservations()
    except Exception as e:
        logger.warning(f"Failed to fetch reservations: {e}")
        return []
