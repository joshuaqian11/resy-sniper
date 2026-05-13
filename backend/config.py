from dataclasses import dataclass, fields
from database import Database

CONFIG_KEYS = [
    "resy_api_key", "resy_auth_token",
    "twilio_account_sid", "twilio_auth_token", "twilio_from",
    "phone_number",
]

@dataclass
class Settings:
    resy_api_key: str = ""
    resy_auth_token: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    phone_number: str = ""

async def load_settings(db: Database) -> Settings:
    raw = await db.get_all_config()
    return Settings(**{k: raw.get(k, "") for k in CONFIG_KEYS})

async def save_settings(db: Database, settings: Settings):
    for f in fields(settings):
        await db.set_config(f.name, getattr(settings, f.name) or "")
