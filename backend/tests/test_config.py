import pytest
from config import Settings, load_settings, save_settings

@pytest.mark.asyncio
async def test_load_settings_returns_defaults_when_empty(tmp_db):
    settings = await load_settings(tmp_db)
    assert settings.resy_api_key == ""
    assert settings.resy_email == ""
    assert settings.phone_number == ""

@pytest.mark.asyncio
async def test_save_and_load_settings(tmp_db):
    s = Settings(
        resy_api_key="key123",
        resy_email="test@example.com",
        twilio_account_sid="AC123",
        twilio_auth_token="twil456",
        twilio_from="+15550001111",
        phone_number="+15559998888",
    )
    await save_settings(tmp_db, s)
    loaded = await load_settings(tmp_db)
    assert loaded.resy_api_key == "key123"
    assert loaded.resy_email == "test@example.com"
    assert loaded.phone_number == "+15559998888"
