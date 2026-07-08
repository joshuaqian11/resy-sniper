import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from snipe import run_snipe, filter_slots

# --- filter_slots tests ---

def test_filter_slots_no_preference():
    slots = [
        {"date": {"start": "2026-06-15 19:00:00"}, "config": {"token": "tok1"}},
        {"date": {"start": "2026-06-15 21:30:00"}, "config": {"token": "tok2"}},
    ]
    assert filter_slots(slots, None, None) == slots

def test_filter_slots_within_window():
    slots = [
        {"date": {"start": "2026-06-15 17:00:00"}, "config": {"token": "too-early"}},
        {"date": {"start": "2026-06-15 19:00:00"}, "config": {"token": "ok"}},
        {"date": {"start": "2026-06-15 22:00:00"}, "config": {"token": "too-late"}},
    ]
    result = filter_slots(slots, "18:00", "21:00")
    assert len(result) == 1
    assert result[0]["config"]["token"] == "ok"

def test_filter_slots_empty_list():
    assert filter_slots([], "18:00", "21:00") == []

# --- run_snipe tests ---

def make_target(preferred_start=None, preferred_end=None):
    return {
        "id": 1,
        "venue_id": "venue1",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "preferred_start": preferred_start,
        "preferred_end": preferred_end,
    }

def make_slot(token="tok1", time="2026-06-15 19:00:00"):
    return {"date": {"start": time}, "config": {"token": token}}

@pytest.mark.asyncio
async def test_run_snipe_books_on_first_slot_found():
    target = make_target()
    mock_db = AsyncMock()
    mock_resy = AsyncMock()
    mock_sms = MagicMock()

    slot = make_slot()
    # find_slots returns a slot on first call, then empty to stop loop
    mock_resy.find_slots = AsyncMock(side_effect=[[slot], [], [], []])
    mock_resy.get_book_token = AsyncMock(return_value="book-tok-xyz")
    mock_resy.book = AsyncMock(return_value={"resy_token": "res-abc"})

    await run_snipe(target, mock_resy, mock_sms, mock_db)

    mock_resy.book.assert_called_once_with("book-tok-xyz")
    mock_db.update_target_booked.assert_called_once_with(1, {"resy_token": "res-abc"})
    mock_sms.send.assert_called_once()
    assert "Carbone" in mock_sms.send.call_args[0][0]

@pytest.mark.asyncio
async def test_run_snipe_retries_book_on_timeout():
    target = make_target()
    mock_db = AsyncMock()
    mock_resy = AsyncMock()
    mock_sms = MagicMock()

    slot = make_slot()
    mock_resy.find_slots = AsyncMock(return_value=[slot])
    mock_resy.get_book_token = AsyncMock(return_value="book-tok-xyz")
    # First call times out, second succeeds
    mock_resy.book = AsyncMock(side_effect=[
        TimeoutError("timeout"),
        {"resy_token": "res-abc"},
    ])

    await run_snipe(target, mock_resy, mock_sms, mock_db)

    assert mock_resy.book.call_count == 2
    mock_db.update_target_booked.assert_called_once()

@pytest.mark.asyncio
async def test_run_snipe_does_not_double_book():
    """booking_in_flight prevents acquiring a second book_token while first is in progress."""
    target = make_target()
    mock_db = AsyncMock()
    mock_resy = AsyncMock()
    mock_sms = MagicMock()

    slot = make_slot()
    mock_resy.find_slots = AsyncMock(return_value=[slot])
    mock_resy.get_book_token = AsyncMock(return_value="book-tok-xyz")

    book_call_count = 0
    async def slow_book(token):
        nonlocal book_call_count
        book_call_count += 1
        await asyncio.sleep(0.05)
        return {"resy_token": "res-abc"}

    mock_resy.book = slow_book

    await run_snipe(target, mock_resy, mock_sms, mock_db)

    assert book_call_count == 1

@pytest.mark.asyncio
async def test_run_snipe_marks_failed_when_no_slots():
    target = make_target()
    mock_db = AsyncMock()
    mock_resy = AsyncMock()
    mock_sms = MagicMock()

    mock_resy.find_slots = AsyncMock(return_value=[])

    with patch("snipe.PHASE1_DURATION", 0.01), patch("snipe.PHASE2_DURATION", 0.01):
        await run_snipe(target, mock_resy, mock_sms, mock_db)

    mock_db.update_target_status.assert_any_call(1, "failed")
    mock_sms.send.assert_called_once()
    assert "Failed" in mock_sms.send.call_args[0][0]

@pytest.mark.asyncio
async def test_run_snipe_fails_on_terminal_book_error():
    target = make_target()
    mock_db = AsyncMock()
    mock_resy = AsyncMock()
    mock_sms = MagicMock()

    slot = make_slot()
    mock_resy.find_slots = AsyncMock(return_value=[slot])
    mock_resy.get_book_token = AsyncMock(return_value="book-tok-xyz")
    # 422 = token expired/invalid — terminal error
    mock_resy.book = AsyncMock(side_effect=Exception("HTTP 422 from /3/book: Token expired"))

    await run_snipe(target, mock_resy, mock_sms, mock_db)

    mock_db.update_target_status.assert_any_call(1, "failed")
