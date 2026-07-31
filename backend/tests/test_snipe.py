import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from snipe import run_snipe, filter_slots, pick_best_slot


# --- filter_slots tests ---

def test_filter_slots_no_window():
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


def test_filter_slots_window_start_only():
    slots = [
        {"date": {"start": "2026-06-15 17:00:00"}, "config": {"token": "early"}},
        {"date": {"start": "2026-06-15 19:00:00"}, "config": {"token": "ok"}},
    ]
    result = filter_slots(slots, "18:00", None)
    assert len(result) == 1
    assert result[0]["config"]["token"] == "ok"


def test_filter_slots_empty_list():
    assert filter_slots([], "18:00", "21:00") == []


# --- pick_best_slot tests ---

def test_pick_best_slot_no_preference():
    slots = [
        {"date": {"start": "2026-06-15 19:00:00"}, "config": {"token": "first"}},
        {"date": {"start": "2026-06-15 20:00:00"}, "config": {"token": "second"}},
    ]
    result = pick_best_slot(slots, None)
    assert result["config"]["token"] == "first"


def test_pick_best_slot_with_preference():
    slots = [
        {"date": {"start": "2026-06-15 18:00:00"}, "config": {"token": "6pm"}},
        {"date": {"start": "2026-06-15 19:30:00"}, "config": {"token": "730pm"}},
        {"date": {"start": "2026-06-15 21:00:00"}, "config": {"token": "9pm"}},
    ]
    result = pick_best_slot(slots, "19:00")
    assert result["config"]["token"] == "730pm"


def test_pick_best_slot_empty_returns_none():
    assert pick_best_slot([], "19:00") is None


# --- run_snipe tests ---

def make_target(**overrides):
    base = {
        "id": "test-uuid-1",
        "venue_id": "venue1",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
    }
    base.update(overrides)
    return base


def make_slot(token="tok1", time="2026-06-15 19:00:00"):
    return {"date": {"start": time}, "config": {"token": token}}


@pytest.mark.asyncio
async def test_run_snipe_books_on_first_slot():
    target = make_target()
    mock_db = MagicMock()
    mock_resy = AsyncMock()

    slot = make_slot()
    mock_resy.find_slots = AsyncMock(side_effect=[[slot], [], []])
    mock_resy.get_book_token = AsyncMock(return_value="book-tok-xyz")
    mock_resy.book = AsyncMock(return_value={"resy_token": "res-abc"})

    await run_snipe(target, mock_resy, mock_db)

    mock_resy.book.assert_called_once_with("book-tok-xyz")
    mock_db.update_target_booked.assert_called_once_with("test-uuid-1", {"resy_token": "res-abc"})


@pytest.mark.asyncio
async def test_run_snipe_retries_book_on_timeout():
    target = make_target()
    mock_db = MagicMock()
    mock_resy = AsyncMock()

    slot = make_slot()
    mock_resy.find_slots = AsyncMock(return_value=[slot])
    mock_resy.get_book_token = AsyncMock(return_value="book-tok-xyz")
    mock_resy.book = AsyncMock(side_effect=[
        httpx.TimeoutException("timeout"),
        {"resy_token": "res-abc"},
    ])

    await run_snipe(target, mock_resy, mock_db)

    assert mock_resy.book.call_count == 2
    mock_db.update_target_booked.assert_called_once()


@pytest.mark.asyncio
async def test_run_snipe_marks_failed_when_no_slots():
    target = make_target()
    mock_db = MagicMock()
    mock_resy = AsyncMock()
    mock_resy.find_slots = AsyncMock(return_value=[])

    with patch("snipe.PHASE1_DURATION", 0.01), patch("snipe.PHASE2_DURATION", 0.01):
        await run_snipe(target, mock_resy, mock_db)

    mock_db.update_target_status.assert_any_call("test-uuid-1", "failed")


@pytest.mark.asyncio
async def test_run_snipe_fails_on_terminal_book_error():
    target = make_target()
    mock_db = MagicMock()
    mock_resy = AsyncMock()

    slot = make_slot()
    mock_resy.find_slots = AsyncMock(return_value=[slot])
    mock_resy.get_book_token = AsyncMock(return_value="book-tok-xyz")
    mock_resy.book = AsyncMock(side_effect=httpx.HTTPStatusError(
        "422", request=MagicMock(), response=MagicMock(status_code=422)
    ))

    await run_snipe(target, mock_resy, mock_db)

    mock_db.update_target_status.assert_any_call("test-uuid-1", "failed")


@pytest.mark.asyncio
async def test_run_snipe_uses_window_filter():
    target = make_target(window_start="18:00", window_end="20:00")
    mock_db = MagicMock()
    mock_resy = AsyncMock()

    early_slot = make_slot(token="too-early", time="2026-06-15 17:00:00")
    good_slot = make_slot(token="good", time="2026-06-15 19:00:00")
    mock_resy.find_slots = AsyncMock(side_effect=[[early_slot, good_slot], []])
    mock_resy.get_book_token = AsyncMock(return_value="book-tok")
    mock_resy.book = AsyncMock(return_value={"resy_token": "res-abc"})

    await run_snipe(target, mock_resy, mock_db)

    mock_resy.get_book_token.assert_called_once_with("good", "2026-06-15", 2)


@pytest.mark.asyncio
async def test_run_snipe_picks_closest_to_preferred_time():
    target = make_target(preferred_time="19:30")
    mock_db = MagicMock()
    mock_resy = AsyncMock()

    slots = [
        make_slot(token="6pm", time="2026-06-15 18:00:00"),
        make_slot(token="730pm", time="2026-06-15 19:30:00"),
        make_slot(token="9pm", time="2026-06-15 21:00:00"),
    ]
    mock_resy.find_slots = AsyncMock(side_effect=[slots, []])
    mock_resy.get_book_token = AsyncMock(return_value="book-tok")
    mock_resy.book = AsyncMock(return_value={"resy_token": "res-abc"})

    await run_snipe(target, mock_resy, mock_db)

    mock_resy.get_book_token.assert_called_once_with("730pm", "2026-06-15", 2)
