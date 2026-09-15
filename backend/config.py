from dataclasses import dataclass, fields
from database import Database

CONFIG_KEYS = [
    "resy_api_key", "resy_auth_token", "resy_email", "resy_password", "resy_cookies",
]


@dataclass
class Settings:
    resy_api_key: str = ""
    resy_auth_token: str = ""
    resy_email: str = ""
    resy_password: str = ""
    resy_cookies: str = ""


def load_settings(db: Database) -> Settings:
    raw = db.get_all_config()
    return Settings(**{k: raw.get(k, "") for k in CONFIG_KEYS})


def save_settings(db: Database, settings: Settings):
    for f in fields(settings):
        db.set_config(f.name, getattr(settings, f.name) or "")
