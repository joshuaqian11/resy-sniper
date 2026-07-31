import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from lambda_handler import handler


def make_event(target_id="test-uuid-1"):
    return {"target_id": target_id}


def test_handler_reads_target_and_runs_snipe(db):
    target_id = db.insert_target({
        "venue_id": "venue1",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00Z",
    })

    db.set_config("resy_api_key", "test-key")
    db.set_config("resy_email", "test@test.com")
    db.set_config("resy_password", "test-pass")

    with patch("lambda_handler.Database") as MockDB, \
         patch("lambda_handler.run_snipe", new_callable=AsyncMock) as mock_snipe, \
         patch("lambda_handler.ResyClient") as MockResy, \
         patch("lambda_handler.asyncio") as mock_asyncio:

        mock_db = MagicMock()
        mock_db.get_target.return_value = db.get_target(target_id)
        mock_db.get_all_config.return_value = db.get_all_config()
        MockDB.return_value = mock_db

        mock_resy_instance = AsyncMock()
        MockResy.return_value = mock_resy_instance

        # Make asyncio.run actually call the coroutine
        mock_asyncio.run = lambda coro: __import__("asyncio").run(coro)
        mock_asyncio.sleep = AsyncMock()

        handler(make_event(target_id), None)

        MockResy.assert_called_once_with(
            api_key="test-key",
            email="test@test.com",
            password="test-pass",
            cookies="",
        )
        mock_snipe.assert_called_once()
        call_args = mock_snipe.call_args
        assert call_args[0][0]["id"] == target_id
        assert call_args[0][0]["venue_name"] == "Carbone"


def test_handler_skips_non_pending_target(db):
    target_id = db.insert_target({
        "venue_id": "venue1",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00Z",
    })
    db.update_target_status(target_id, "booked")

    with patch("lambda_handler.Database") as MockDB, \
         patch("lambda_handler.run_snipe", new_callable=AsyncMock) as mock_snipe:

        mock_db = MagicMock()
        mock_db.get_target.return_value = db.get_target(target_id)
        MockDB.return_value = mock_db

        handler(make_event(target_id), None)

        mock_snipe.assert_not_called()


def test_handler_returns_error_for_missing_target(db):
    with patch("lambda_handler.Database") as MockDB:
        mock_db = MagicMock()
        mock_db.get_target.return_value = None
        MockDB.return_value = mock_db

        result = handler(make_event("nonexistent"), None)
        assert result["statusCode"] == 404
