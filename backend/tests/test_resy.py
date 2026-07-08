import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from resy import ResyClient

API_KEY = "test-api-key"


def _mock_response(status: int, json_data: dict | None = None, text: str = ""):
    """Create a mock that behaves like a Playwright APIResponse."""
    resp = MagicMock()
    resp.status = status
    resp.ok = 200 <= status < 300
    resp.json = AsyncMock(return_value=json_data or {})
    resp.text = AsyncMock(return_value=text)
    return resp


@pytest.fixture
def client():
    c = ResyClient(api_key=API_KEY, email="test@example.com", password="pass123")
    # Pre-set auth_token so connect() skips login and pre-warm
    c.auth_token = "test-auth-token"
    # Inject a mock request context so no real browser is launched
    c._request = MagicMock()
    return c


@pytest.mark.asyncio
async def test_find_slots_returns_slots(client):
    mock_json = {
        "results": {
            "venues": [{
                "slots": [
                    {
                        "date": {"start": "2026-06-15 19:00:00"},
                        "config": {"token": "rgs://resy/abc123", "type": "DINING_ROOM"},
                        "availability": "available",
                    }
                ]
            }]
        }
    }
    client._request.get = AsyncMock(return_value=_mock_response(200, mock_json))
    slots = await client.find_slots("venue1", "2026-06-15", 2)
    assert len(slots) == 1
    assert slots[0]["config"]["token"] == "rgs://resy/abc123"


@pytest.mark.asyncio
async def test_find_slots_returns_empty_when_no_venues(client):
    client._request.get = AsyncMock(
        return_value=_mock_response(200, {"results": {"venues": []}})
    )
    slots = await client.find_slots("venue1", "2026-06-15", 2)
    assert slots == []


@pytest.mark.asyncio
async def test_get_book_token(client):
    mock_json = {"book_token": {"value": "book-tok-xyz", "date_expires": "2026-06-15T09:05:00Z"}}
    client._request.get = AsyncMock(return_value=_mock_response(200, mock_json))
    token = await client.get_book_token("rgs://resy/abc123", "2026-06-15", 2)
    assert token == "book-tok-xyz"


@pytest.mark.asyncio
async def test_book_returns_reservation(client):
    mock_json = {"resy_token": "res-token-abc", "reservation_id": 99}
    client._request.post = AsyncMock(return_value=_mock_response(200, mock_json))
    result = await client.book("book-tok-xyz")
    assert result["resy_token"] == "res-token-abc"


@pytest.mark.asyncio
async def test_book_raises_on_4xx(client):
    client._request.post = AsyncMock(
        return_value=_mock_response(422, text="Token expired")
    )
    with pytest.raises(Exception, match="HTTP 422"):
        await client.book("expired-token")


@pytest.mark.asyncio
async def test_get_reservations(client):
    mock_json = {"reservations": [{"resy_token": "res-abc"}]}
    client._request.get = AsyncMock(return_value=_mock_response(200, mock_json))
    reservations = await client.get_reservations()
    assert len(reservations) == 1


@pytest.mark.asyncio
async def test_auth_header_is_sent(client):
    client._request.get = AsyncMock(
        return_value=_mock_response(200, {"results": {"venues": []}})
    )
    await client.find_slots("v1", "2026-06-15", 2)
    call_kwargs = client._request.get.call_args
    headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
    assert headers["authorization"] == f'ResyAPI api_key="{API_KEY}"'
    assert headers["x-resy-auth-token"] == "test-auth-token"


@pytest.mark.asyncio
async def test_login_sets_auth_token(client):
    client.auth_token = ""
    login_response = _mock_response(200, {
        "legacy_token": "fresh-token-123",
        "payment_method_id": 42,
    })
    client._request.post = AsyncMock(return_value=login_response)
    await client.login()
    assert client.auth_token == "fresh-token-123"
    assert client.payment_method_id == 42


@pytest.mark.asyncio
async def test_auto_refresh_on_401(client):
    """GET that returns 401 triggers login() then retries."""
    first_resp = _mock_response(401, text="Unauthorized")
    second_resp = _mock_response(200, {"results": {"venues": []}})
    client._request.get = AsyncMock(side_effect=[first_resp, second_resp])

    login_resp = _mock_response(200, {"legacy_token": "refreshed-token", "payment_method_id": 1})
    client._request.post = AsyncMock(return_value=login_resp)

    slots = await client.find_slots("venue1", "2026-06-15", 2)
    assert slots == []
    assert client.auth_token == "refreshed-token"
    assert client._request.get.call_count == 2
