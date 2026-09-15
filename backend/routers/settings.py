from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from auth import require_api_key
from config import Settings, load_settings, save_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsBody(BaseModel):
    resy_api_key: str = ""
    resy_auth_token: str = ""
    resy_email: str = ""
    resy_password: str = ""
    resy_cookies: str = ""


@router.get("", dependencies=[Depends(require_api_key)])
async def get_settings(request: Request):
    settings = load_settings(request.app.state.db)
    return settings.__dict__


@router.put("", dependencies=[Depends(require_api_key)])
async def update_settings(body: SettingsBody, request: Request):
    settings = Settings(**body.model_dump())
    save_settings(request.app.state.db, settings)
    return settings.__dict__
