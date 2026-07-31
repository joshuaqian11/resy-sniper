import pytest
from config import Settings, load_settings, save_settings


def test_load_settings_returns_defaults_when_empty(db):
    settings = load_settings(db)
    assert settings.resy_api_key == ""
    assert settings.resy_email == ""
    assert settings.resy_password == ""
    assert settings.resy_cookies == ""


def test_save_and_load_settings(db):
    s = Settings(
        resy_api_key="key123",
        resy_email="test@test.com",
        resy_password="pass456",
        resy_cookies="cookie-data",
    )
    save_settings(db, s)
    loaded = load_settings(db)
    assert loaded.resy_api_key == "key123"
    assert loaded.resy_email == "test@test.com"
    assert loaded.resy_password == "pass456"
    assert loaded.resy_cookies == "cookie-data"
