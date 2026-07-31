import pytest
from database import Database


def test_insert_and_fetch_target(db):
    target_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00Z",
        "preferred_time": "19:00",
        "window_start": "18:00",
        "window_end": "21:00",
    })
    assert isinstance(target_id, str)
    targets = db.get_all_targets()
    assert len(targets) == 1
    assert targets[0]["venue_name"] == "Carbone"
    assert targets[0]["status"] == "pending"
    assert targets[0]["party_size"] == 2


def test_get_target_by_id(db):
    target_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00Z",
    })
    target = db.get_target(target_id)
    assert target is not None
    assert target["venue_name"] == "Carbone"


def test_get_target_missing_returns_none(db):
    assert db.get_target("nonexistent-id") is None


def test_update_target_status(db):
    target_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00Z",
    })
    db.update_target_status(target_id, "sniping")
    target = db.get_target(target_id)
    assert target["status"] == "sniping"


def test_update_target_booked(db):
    target_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00Z",
    })
    db.update_target_booked(target_id, {"resy_token": "abc123"})
    target = db.get_target(target_id)
    assert target["status"] == "booked"
    assert '"resy_token"' in target["reservation_details"]
    assert target["booked_at"] is not None


def test_delete_pending_target(db):
    target_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00Z",
    })
    assert db.delete_target_if_pending(target_id) is True
    assert db.get_target(target_id) is None


def test_delete_non_pending_target_fails(db):
    target_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00Z",
    })
    db.update_target_status(target_id, "sniping")
    assert db.delete_target_if_pending(target_id) is False
    assert db.get_target(target_id) is not None


def test_complete_past_targets(db):
    past_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2020-01-01",
        "party_size": 2,
        "opening_time": "2019-12-02T09:00:00Z",
    })
    db.update_target_status(past_id, "booked")

    future_id = db.insert_target({
        "venue_id": "456",
        "venue_name": "Le Bernardin",
        "date": "2099-06-15",
        "party_size": 4,
        "opening_time": "2099-05-16T09:00:00Z",
    })

    db.complete_past_targets()

    past = db.get_target(past_id)
    assert past["status"] == "completed"

    future = db.get_target(future_id)
    assert future["status"] == "pending"


def test_config_set_and_get(db):
    db.set_config("resy_api_key", "my-key")
    assert db.get_config("resy_api_key") == "my-key"


def test_config_missing_returns_none(db):
    assert db.get_config("nonexistent") is None


def test_config_get_all(db):
    db.set_config("resy_api_key", "key1")
    db.set_config("resy_email", "test@test.com")
    config = db.get_all_config()
    assert config["resy_api_key"] == "key1"
    assert config["resy_email"] == "test@test.com"
