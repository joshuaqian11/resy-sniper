import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from resy import ResyClient

API_KEY = "test-api-key"
EMAIL = "test@test.com"
PASSWORD = "test-password"


def make_mock_response(status=200, body=None):
    """Create a mock Playwright APIResponse."""
    resp = AsyncMock()
    resp.status = status
    resp.ok = 200 <= status < 300
    resp.text = AsyncMock(return_value=json.dumps(body or {}))
    resp.json = AsyncMock(return_value=body or {})
    return resp


@pytest.fixture
def mock_request():
    """Mock Playwright APIRequestContext."""
    return AsyncMock()


@pytest.fixture
def client(mock_request):
    """Create a ResyClient with mocked Playwright internals."""
    c = ResyClient(api_key=API_KEY, email=EMAIL, password=PASSWORD)
    c._request = mock_request
    c._playwright = MagicMock()
    c._browser = AsyncMock()
    c._context = MagicMock()
    return c


@pytest.mark.asyncio
async def test_login_sets_auth_token(client, mock_request):
    mock_request.post.return_value = make_mock_response(200, {
        "legacy_token": "auth-tok-123",
        "payment_method_id": 42,
    })
    await client._login()
    assert client.auth_token == "auth-tok-123"
    assert client.payment_method_id == 42


@pytest.mark.asyncio
async def test_find_slots_returns_slots(client, mock_request):
    client.auth_token = "pre-set-token"
    mock_request.get.return_value = make_mock_response(200, {
        "results": {
            "venues": [{
                "slots": [
                    {
                        "date": {"start": "2026-06-15 19:00:00"},
                        "config": {"token": "rgs://resy/abc123"},
                    }
                ]
            }]
        }
    })
    slots = await client.find_slots("venue1", "2026-06-15", 2)
    assert len(slots) == 1
    assert slots[0]["config"]["token"] == "rgs://resy/abc123"


@pytest.mark.asyncio
async def test_find_slots_empty_venues(client, mock_request):
    client.auth_token = "pre-set-token"
    mock_request.get.return_value = make_mock_response(200, {
        "results": {"venues": []}
    })
    slots = await client.find_slots("venue1", "2026-06-15", 2)
    assert slots == []


@pytest.mark.asyncio
async def test_get_book_token(client, mock_request):
    client.auth_token = "pre-set-token"
    mock_request.get.return_value = make_mock_response(200, {
        "book_token": {"value": "book-tok-xyz", "date_expires": "2026-06-15T09:05:00Z"}
    })
    token = await client.get_book_token("rgs://resy/abc123", "2026-06-15", 2)
    assert token == "book-tok-xyz"


@pytest.mark.asyncio
async def test_book_returns_reservation(client, mock_request):
    client.auth_token = "pre-set-token"
    mock_request.post.return_value = make_mock_response(200, {
        "resy_token": "res-token-abc", "reservation_id": 99
    })
    result = await client.book("book-tok-xyz")
    assert result["resy_token"] == "res-token-abc"


@pytest.mark.asyncio
async def test_book_raises_on_4xx(client, mock_request):
    client.auth_token = "pre-set-token"
    # First post call (book) returns 422, no 401 retry
    mock_request.post.return_value = make_mock_response(422, {"message": "Token expired"})
    with pytest.raises(Exception, match="HTTP 422"):
        await client.book("expired-token")


@pytest.mark.asyncio
async def test_auth_header_format(client, mock_request):
    client.auth_token = "auth-tok-123"
    mock_request.get.return_value = make_mock_response(200, {
        "results": {"venues": []}
    })
    await client.find_slots("v1", "2026-06-15", 2)
    call_args = mock_request.get.call_args
    headers = call_args.kwargs.get("headers") or call_args[1].get("headers")
    assert headers["authorization"] == 'ResyAPI api_key="test-api-key"'


@pytest.mark.asyncio
async def test_connect_calls_playwright():
    mock_pw_instance = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_pw_instance.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context

    mock_pw_cm = AsyncMock()
    mock_pw_cm.start.return_value = mock_pw_instance

    with patch("resy.async_playwright", return_value=mock_pw_cm):
        client = ResyClient(api_key=API_KEY, auth_token="pre-set")
        await client.connect()
        mock_pw_instance.chromium.launch.assert_called_once_with(headless=True)
        await client.close()
