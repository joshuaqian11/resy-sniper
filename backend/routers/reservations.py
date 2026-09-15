import logging
from fastapi import APIRouter, Depends, Request
from auth import require_api_key
from config import load_settings
from resy import ResyClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reservations", tags=["reservations"])


@router.get("", dependencies=[Depends(require_api_key)])
async def get_reservations(request: Request):
    db = request.app.state.db
    settings = load_settings(db)
    if not settings.resy_api_key:
        return []
    client = ResyClient(
        api_key=settings.resy_api_key,
        auth_token=settings.resy_auth_token,
        email=settings.resy_email,
        password=settings.resy_password,
        cookies=settings.resy_cookies,
    )
    try:
        await client.connect()
        return await client.get_reservations()
    except Exception as e:
        logger.error(f"Failed to fetch reservations: {e}")
        return []
    finally:
        await client.close()
