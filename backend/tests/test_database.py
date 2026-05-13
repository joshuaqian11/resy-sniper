import pytest
import pytest_asyncio
from database import Database

@pytest.mark.asyncio
async def test_tables_created(tmp_db):
    rows = await tmp_db.execute_fetchall(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    names = {r["name"] for r in rows}
    assert "targets" in names
    assert "config" in names

@pytest.mark.asyncio
async def test_insert_and_fetch_target(tmp_db):
    await tmp_db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00",
        "preferred_start": "19:00",
        "preferred_end": "21:00",
    })
    targets = await tmp_db.get_all_targets()
    assert len(targets) == 1
    assert targets[0]["venue_name"] == "Carbone"
    assert targets[0]["status"] == "pending"

@pytest.mark.asyncio
async def test_update_target_status(tmp_db):
    await tmp_db.insert_target({
        "venue_id": "123", "venue_name": "Carbone",
        "date": "2026-06-15", "party_size": 2,
        "opening_time": "2026-05-16T09:00:00",
        "preferred_start": None, "preferred_end": None,
    })
    targets = await tmp_db.get_all_targets()
    target_id = targets[0]["id"]
    await tmp_db.update_target_status(target_id, "sniping")
    updated = await tmp_db.get_target(target_id)
    assert updated["status"] == "sniping"

@pytest.mark.asyncio
async def test_update_target_booked(tmp_db):
    await tmp_db.insert_target({
        "venue_id": "123", "venue_name": "Carbone",
        "date": "2026-06-15", "party_size": 2,
        "opening_time": "2026-05-16T09:00:00",
        "preferred_start": None, "preferred_end": None,
    })
    targets = await tmp_db.get_all_targets()
    target_id = targets[0]["id"]
    await tmp_db.update_target_booked(target_id, {"resy_token": "abc123"})
    updated = await tmp_db.get_target(target_id)
    assert updated["status"] == "booked"
    assert updated["reservation_details"] == '{"resy_token": "abc123"}'
    assert updated["booked_at"] is not None

@pytest.mark.asyncio
async def test_delete_pending_target(tmp_db):
    await tmp_db.insert_target({
        "venue_id": "123", "venue_name": "Carbone",
        "date": "2026-06-15", "party_size": 2,
        "opening_time": "2026-05-16T09:00:00",
        "preferred_start": None, "preferred_end": None,
    })
    targets = await tmp_db.get_all_targets()
    target_id = targets[0]["id"]
    deleted = await tmp_db.delete_target_if_pending(target_id)
    assert deleted is True
    assert await tmp_db.get_target(target_id) is None

@pytest.mark.asyncio
async def test_delete_non_pending_target_fails(tmp_db):
    await tmp_db.insert_target({
        "venue_id": "123", "venue_name": "Carbone",
        "date": "2026-06-15", "party_size": 2,
        "opening_time": "2026-05-16T09:00:00",
        "preferred_start": None, "preferred_end": None,
    })
    targets = await tmp_db.get_all_targets()
    target_id = targets[0]["id"]
    await tmp_db.update_target_status(target_id, "sniping")
    deleted = await tmp_db.delete_target_if_pending(target_id)
    assert deleted is False

@pytest.mark.asyncio
async def test_config_set_and_get(tmp_db):
    await tmp_db.set_config("resy_api_key", "my-key")
    value = await tmp_db.get_config("resy_api_key")
    assert value == "my-key"

@pytest.mark.asyncio
async def test_config_missing_returns_none(tmp_db):
    value = await tmp_db.get_config("nonexistent")
    assert value is None
