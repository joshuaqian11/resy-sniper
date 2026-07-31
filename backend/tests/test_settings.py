import os
import pytest
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from database import Database

@pytest.fixture(autouse=True)
def _set_api_key():
    os.environ["DASHBOARD_API_KEY"] = "test-key"
    yield
    os.environ["DASHBOARD_API_KEY"] = "test-key"


@pytest.fixture
def test_app(db):
    from main import create_app
    mock_aws_client = MagicMock()
    app = create_app(db=db, aws_client=mock_aws_client)
    return app, db


@pytest.mark.asyncio
async def test_get_settings_empty(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/settings", headers={"x-api-key": "test-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resy_api_key"] == ""
    assert "twilio_account_sid" not in data


@pytest.mark.asyncio
async def test_put_settings(test_app):
    app, db = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put("/api/settings", headers={"x-api-key": "test-key"}, json={
            "resy_api_key": "key123",
            "resy_email": "test@test.com",
            "resy_password": "pass456",
            "resy_cookies": "",
        })
    assert resp.status_code == 200
    assert db.get_config("resy_api_key") == "key123"
    assert db.get_config("resy_email") == "test@test.com"
