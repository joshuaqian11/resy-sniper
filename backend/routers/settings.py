import dataclasses
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from auth import require_api_key
from config import Settings, load_settings, save_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])

class SettingsBody(BaseModel):
    resy_api_key: str = ""
    resy_email: str = ""
    resy_password: str = ""
    resy_cookies: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    phone_number: str = ""

@router.get("", dependencies=[Depends(require_api_key)])
async def get_settings(request: Request):
    settings = await load_settings(request.app.state.db)
    return dataclasses.asdict(settings)

@router.put("", dependencies=[Depends(require_api_key)])
async def update_settings(body: SettingsBody, request: Request):
    settings = Settings(**body.model_dump())
    await save_settings(request.app.state.db, settings)
    # Update the live ResyClient so future jobs use the new credentials
    resy_client = request.app.state.scheduler.resy_client
    resy_client.api_key = settings.resy_api_key
    resy_client.email = settings.resy_email
    resy_client.password = settings.resy_password
    resy_client.cookies = settings.resy_cookies
    return dataclasses.asdict(settings)
