import pytest
import pytest_asyncio
import os
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from database import Database

os.environ["DASHBOARD_API_KEY"] = "test-key"

@pytest_asyncio.fixture
async def test_app(tmp_path):
    os.environ["DASHBOARD_API_KEY"] = "test-key"
    from main import create_app
    db = Database(str(tmp_path / "test.db"))
    await db.init()
    mock_scheduler = MagicMock()
    mock_aws = MagicMock()
    app = create_app(db=db, scheduler=mock_scheduler, aws_client=mock_aws)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, db

@pytest.mark.asyncio
async def test_get_settings_empty(test_app):
    client, _ = test_app
    resp = await client.get("/api/settings", headers={"x-api-key": "test-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resy_api_key"] == ""
    assert data["phone_number"] == ""

@pytest.mark.asyncio
async def test_put_settings(test_app):
    client, db = test_app
    resp = await client.put("/api/settings", headers={"x-api-key": "test-key"}, json={
        "resy_api_key": "key123",
        "resy_email": "test@example.com",
        "resy_password": "pass123",
        "resy_cookies": "",
        "twilio_account_sid": "AC123",
        "twilio_auth_token": "twiltok",
        "twilio_from": "+15550001111",
        "phone_number": "+15559998888",
    })
    assert resp.status_code == 200
    loaded = await db.get_config("resy_api_key")
    assert loaded == "key123"
