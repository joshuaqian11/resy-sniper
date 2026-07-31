import pytest
import respx
import httpx
from resy import ResyClient

API_KEY = "test-api-key"
EMAIL = "test@test.com"
PASSWORD = "test-password"


@pytest.fixture
def client():
    return ResyClient(api_key=API_KEY, email=EMAIL, password=PASSWORD)


@pytest.mark.asyncio
async def test_login_sets_auth_token(client):
    with respx.mock:
        respx.post("https://api.resy.com/3/auth/password").mock(
            return_value=httpx.Response(200, json={
                "token": "auth-tok-123",
                "payment_method_id": 42,
            })
        )
        await client.connect()
        assert client.auth_token == "auth-tok-123"
        assert client.payment_method_id == 42
        await client.close()


@pytest.mark.asyncio
async def test_find_slots_returns_slots(client):
    mock_find = {
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
    }
    with respx.mock:
        respx.post("https://api.resy.com/3/auth/password").mock(
            return_value=httpx.Response(200, json={
                "token": "auth-tok",
                "payment_method_id": 1,
            })
        )
        respx.get("https://api.resy.com/4/find").mock(
            return_value=httpx.Response(200, json=mock_find)
        )
        await client.connect()
        slots = await client.find_slots("venue1", "2026-06-15", 2)
        await client.close()
    assert len(slots) == 1
    assert slots[0]["config"]["token"] == "rgs://resy/abc123"


@pytest.mark.asyncio
async def test_find_slots_empty_venues(client):
    with respx.mock:
        respx.post("https://api.resy.com/3/auth/password").mock(
            return_value=httpx.Response(200, json={
                "token": "auth-tok",
                "payment_method_id": 1,
            })
        )
        respx.get("https://api.resy.com/4/find").mock(
            return_value=httpx.Response(200, json={"results": {"venues": []}})
        )
        await client.connect()
        slots = await client.find_slots("venue1", "2026-06-15", 2)
        await client.close()
    assert slots == []


@pytest.mark.asyncio
async def test_get_book_token(client):
    mock_details = {
        "book_token": {"value": "book-tok-xyz", "date_expires": "2026-06-15T09:05:00Z"}
    }
    with respx.mock:
        respx.post("https://api.resy.com/3/auth/password").mock(
            return_value=httpx.Response(200, json={
                "token": "auth-tok",
                "payment_method_id": 1,
            })
        )
        respx.get("https://api.resy.com/3/details").mock(
            return_value=httpx.Response(200, json=mock_details)
        )
        await client.connect()
        token = await client.get_book_token("rgs://resy/abc123", "2026-06-15", 2)
        await client.close()
    assert token == "book-tok-xyz"


@pytest.mark.asyncio
async def test_book_returns_reservation(client):
    mock_book = {"resy_token": "res-token-abc", "reservation_id": 99}
    with respx.mock:
        respx.post("https://api.resy.com/3/auth/password").mock(
            return_value=httpx.Response(200, json={
                "token": "auth-tok",
                "payment_method_id": 1,
            })
        )
        respx.post("https://api.resy.com/3/book").mock(
            return_value=httpx.Response(200, json=mock_book)
        )
        await client.connect()
        result = await client.book("book-tok-xyz")
        await client.close()
    assert result["resy_token"] == "res-token-abc"


@pytest.mark.asyncio
async def test_book_raises_on_4xx(client):
    with respx.mock:
        respx.post("https://api.resy.com/3/auth/password").mock(
            return_value=httpx.Response(200, json={
                "token": "auth-tok",
                "payment_method_id": 1,
            })
        )
        respx.post("https://api.resy.com/3/book").mock(
            return_value=httpx.Response(422, json={"message": "Token expired"})
        )
        await client.connect()
        with pytest.raises(httpx.HTTPStatusError):
            await client.book("expired-token")
        await client.close()


@pytest.mark.asyncio
async def test_auth_header_format(client):
    captured = {}
    with respx.mock:
        respx.post("https://api.resy.com/3/auth/password").mock(
            return_value=httpx.Response(200, json={
                "token": "auth-tok-123",
                "payment_method_id": 1,
            })
        )

        def capture(request):
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"results": {"venues": []}})

        respx.get("https://api.resy.com/4/find").mock(side_effect=capture)
        await client.connect()
        await client.find_slots("v1", "2026-06-15", 2)
        await client.close()
    assert captured["auth"] == 'ResyKey api_key="test-api-key"'


@pytest.mark.asyncio
async def test_connect_with_cookies_skips_login():
    client = ResyClient(api_key=API_KEY, cookies="resy_auth_token=cookie-tok-456")
    with respx.mock:
        respx.get("https://api.resy.com/4/find").mock(
            return_value=httpx.Response(200, json={"results": {"venues": []}})
        )
        await client.connect(venue_id="v1", date="2026-06-15", party_size=2)
        assert client.auth_token == "cookie-tok-456"
        await client.close()
