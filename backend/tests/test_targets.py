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
def mock_aws_client():
    client = MagicMock()
    client.create_start_rule = MagicMock()
    client.delete_rule = MagicMock()
    return client


@pytest.fixture
def test_app(db, mock_aws_client):
    from main import create_app
    app = create_app(db=db, aws_client=mock_aws_client)
    return app, db, mock_aws_client


@pytest.mark.asyncio
async def test_list_targets_empty(test_app):
    app, db, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/targets", headers={"x-api-key": "test-key"})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_add_target(test_app):
    app, db, mock_aws_client = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/targets", headers={"x-api-key": "test-key"}, json={
            "venue_id": "123",
            "venue_name": "Carbone",
            "date": "2026-06-15",
            "party_size": 2,
            "opening_time": "2099-05-16T09:00:00Z",
            "preferred_time": "19:00",
            "window_start": "18:00",
            "window_end": "21:00",
        })
    assert resp.status_code == 201
    data = resp.json()
    assert data["venue_name"] == "Carbone"
    assert data["status"] == "pending"
    assert data["preferred_time"] == "19:00"
    assert data["window_start"] == "18:00"
    mock_aws_client.create_start_rule.assert_called_once()


@pytest.mark.asyncio
async def test_delete_pending_target(test_app):
    app, db, mock_aws_client = test_app
    target_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2099-05-16T09:00:00Z",
    })
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"/api/targets/{target_id}", headers={"x-api-key": "test-key"})
    assert resp.status_code == 204
    mock_aws_client.delete_rule.assert_called_once()


@pytest.mark.asyncio
async def test_unauthorized_request_rejected(test_app):
    app, _, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/targets", headers={"x-api-key": "wrong"})
    assert resp.status_code == 401
