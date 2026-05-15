import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from scheduler import SnipeScheduler

@pytest.fixture
def mock_deps():
    db = AsyncMock()
    resy = AsyncMock()
    sms = MagicMock()
    aws = MagicMock()
    return db, resy, sms, aws

@pytest.mark.asyncio
async def test_schedule_future_target_adds_job(mock_deps):
    db, resy, sms, aws = mock_deps
    scheduler = SnipeScheduler(db=db, resy_client=resy, sms_client=sms, aws_client=aws)
    scheduler.start()

    future_time = datetime.now(timezone.utc) + timedelta(hours=1)
    target = {
        "id": 1, "venue_name": "Carbone", "venue_id": "v1",
        "date": "2026-06-15", "party_size": 2,
        "opening_time": future_time.isoformat(),
        "preferred_start": None, "preferred_end": None,
    }
    scheduler.schedule_target(target)
    assert scheduler.has_job(1)
    scheduler.shutdown()

@pytest.mark.asyncio
async def test_cancel_removes_job(mock_deps):
    db, resy, sms, aws = mock_deps
    scheduler = SnipeScheduler(db=db, resy_client=resy, sms_client=sms, aws_client=aws)
    scheduler.start()

    future_time = datetime.now(timezone.utc) + timedelta(hours=1)
    target = {
        "id": 2, "venue_name": "Carbone", "venue_id": "v1",
        "date": "2026-06-15", "party_size": 2,
        "opening_time": future_time.isoformat(),
        "preferred_start": None, "preferred_end": None,
    }
    scheduler.schedule_target(target)
    assert scheduler.has_job(2)
    scheduler.cancel_target(2)
    assert not scheduler.has_job(2)
    scheduler.shutdown()

@pytest.mark.asyncio
async def test_schedule_past_target_is_skipped(mock_deps):
    db, resy, sms, aws = mock_deps
    scheduler = SnipeScheduler(db=db, resy_client=resy, sms_client=sms, aws_client=aws)
    scheduler.start()

    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    target = {
        "id": 3, "venue_name": "Carbone", "venue_id": "v1",
        "date": "2026-06-15", "party_size": 2,
        "opening_time": past_time.isoformat(),
        "preferred_start": None, "preferred_end": None,
    }
    scheduler.schedule_target(target)
    assert not scheduler.has_job(3)
    scheduler.shutdown()
