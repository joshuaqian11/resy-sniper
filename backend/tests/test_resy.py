import pytest
import respx
import httpx
from resy import ResyClient

API_KEY = "test-api-key"
AUTH_TOKEN = "test-auth-token"
AUTH_HEADER = f'ResyKey apikey="{API_KEY}",auth_token="{AUTH_TOKEN}"'

@pytest.fixture
def client():
    return ResyClient(api_key=API_KEY, auth_token=AUTH_TOKEN)

@pytest.mark.asyncio
async def test_find_slots_returns_slots(client):
    mock_response = {
        "results": {
            "venues": [{
                "slots": [
                    {
                        "date": {"start": "2026-06-15 19:00:00"},
                        "config": {"token": "rgs://resy/abc123", "type": "DINING_ROOM"},
                        "availability": "available"
                    }
                ]
            }]
        }
    }
    with respx.mock:
        respx.get("https://api.resy.com/4/find").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        await client.connect()
        slots = await client.find_slots("venue1", "2026-06-15", 2)
        await client.close()
    assert len(slots) == 1
    assert slots[0]["config"]["token"] == "rgs://resy/abc123"

@pytest.mark.asyncio
async def test_find_slots_returns_empty_when_no_venues(client):
    with respx.mock:
        respx.get("https://api.resy.com/4/find").mock(
            return_value=httpx.Response(200, json={"results": {"venues": []}})
        )
        await client.connect()
        slots = await client.find_slots("venue1", "2026-06-15", 2)
        await client.close()
    assert slots == []

@pytest.mark.asyncio
async def test_get_book_token(client):
    mock_response = {"book_token": {"value": "book-tok-xyz", "date_expires": "2026-06-15T09:05:00Z"}}
    with respx.mock:
        respx.post("https://api.resy.com/3/details").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        await client.connect()
        token = await client.get_book_token("rgs://resy/abc123", "2026-06-15", 2)
        await client.close()
    assert token == "book-tok-xyz"

@pytest.mark.asyncio
async def test_book_returns_reservation(client):
    mock_response = {"resy_token": "res-token-abc", "reservation_id": 99}
    with respx.mock:
        respx.post("https://api.resy.com/3/book").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        await client.connect()
        result = await client.book("book-tok-xyz")
        await client.close()
    assert result["resy_token"] == "res-token-abc"

@pytest.mark.asyncio
async def test_book_raises_on_4xx(client):
    with respx.mock:
        respx.post("https://api.resy.com/3/book").mock(
            return_value=httpx.Response(422, json={"message": "Token expired"})
        )
        await client.connect()
        with pytest.raises(httpx.HTTPStatusError):
            await client.book("expired-token")
        await client.close()

@pytest.mark.asyncio
async def test_get_reservations(client):
    mock_response = {"reservations": [{"resy_token": "res-abc"}]}
    with respx.mock:
        respx.get("https://api.resy.com/3/user/reservations").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        await client.connect()
        reservations = await client.get_reservations()
        await client.close()
    assert len(reservations) == 1

@pytest.mark.asyncio
async def test_auth_header_is_sent(client):
    captured = {}
    with respx.mock:
        def capture(request):
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"results": {"venues": []}})
        respx.get("https://api.resy.com/4/find").mock(side_effect=capture)
        await client.connect()
        await client.find_slots("v1", "2026-06-15", 2)
        await client.close()
    assert captured["auth"] == AUTH_HEADER
