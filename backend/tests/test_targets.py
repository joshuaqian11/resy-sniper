import pytest
import pytest_asyncio
import os
from unittest.mock import MagicMock, AsyncMock, patch
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
    mock_scheduler.schedule_target = MagicMock()
    mock_scheduler.cancel_target = MagicMock()
    mock_aws = MagicMock()
    app = create_app(db=db, scheduler=mock_scheduler, aws_client=mock_aws)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, db, mock_scheduler

@pytest.mark.asyncio
async def test_list_targets_empty(test_app):
    client, db, _ = test_app
    resp = await client.get("/api/targets", headers={"x-api-key": "test-key"})
    assert resp.status_code == 200
    assert resp.json() == []

@pytest.mark.asyncio
async def test_add_target(test_app):
    client, db, mock_scheduler = test_app
    resp = await client.post("/api/targets", headers={"x-api-key": "test-key"}, json={
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2099-05-16T09:00:00",
        "preferred_start": "19:00",
        "preferred_end": "21:00",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["venue_name"] == "Carbone"
    assert data["status"] == "pending"
    mock_scheduler.schedule_target.assert_called_once()

@pytest.mark.asyncio
async def test_delete_pending_target(test_app):
    client, db, mock_scheduler = test_app
    await client.post("/api/targets", headers={"x-api-key": "test-key"}, json={
        "venue_id": "123", "venue_name": "Carbone",
        "date": "2026-06-15", "party_size": 2,
        "opening_time": "2099-05-16T09:00:00",
        "preferred_start": None, "preferred_end": None,
    })
    targets = await db.get_all_targets()
    target_id = targets[0]["id"]
    resp = await client.delete(f"/api/targets/{target_id}", headers={"x-api-key": "test-key"})
    assert resp.status_code == 204
    mock_scheduler.cancel_target.assert_called_once_with(target_id)

@pytest.mark.asyncio
async def test_unauthorized_request_rejected(test_app):
    client, _, _ = test_app
    resp = await client.get("/api/targets", headers={"x-api-key": "wrong"})
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_delete_non_pending_target_rejected(test_app):
    client, db, _ = test_app
    # Insert a target directly and set its status to 'booked'
    target_id = await db.insert_target({
        "venue_id": "999", "venue_name": "Test", "date": "2026-06-15",
        "party_size": 2, "opening_time": "2099-05-16T09:00:00",
        "preferred_start": None, "preferred_end": None,
    })
    await db.update_target_status(target_id, "booked")
    resp = await client.delete(f"/api/targets/{target_id}", headers={"x-api-key": "test-key"})
    assert resp.status_code == 409
