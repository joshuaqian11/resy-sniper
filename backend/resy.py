import httpx
from typing import Optional

class ResyClient:
    BASE_URL = "https://api.resy.com"

    def __init__(self, api_key: str, auth_token: str):
        self.api_key = api_key
        self.auth_token = auth_token
        self._client: Optional[httpx.AsyncClient] = None

    def _auth_header(self) -> str:
        return f'ResyKey apikey="{self.api_key}",auth_token="{self.auth_token}"'

    async def connect(self):
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": self._auth_header(),
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=10.0,
        )
        # Pre-warm the connection (establishes TCP/TLS connection)
        try:
            await self._client.get("/4/find", params={
                "lat": 0, "long": 0, "day": "2000-01-01", "party_size": 1
            })
        except Exception:
            pass  # Pre-warm failure is non-fatal

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def find_slots(self, venue_id: str, date: str, party_size: int) -> list[dict]:
        resp = await self._client.get("/4/find", params={
            "lat": 0,
            "long": 0,
            "day": date,
            "party_size": party_size,
            "venue_id": venue_id,
        })
        resp.raise_for_status()
        venues = resp.json().get("results", {}).get("venues", [])
        if not venues:
            return []
        return venues[0].get("slots", [])

    async def get_book_token(self, config_id: str, date: str, party_size: int) -> str:
        resp = await self._client.post("/3/details", json={
            "commit": 1,
            "config_id": config_id,
            "day": date,
            "party_size": party_size,
        })
        resp.raise_for_status()
        return resp.json()["book_token"]["value"]

    async def book(self, book_token: str) -> dict:
        resp = await self._client.post("/3/book", json={
            "book_token": book_token,
            "struct_payment_method": '{"id": 0}',
            "source_id": "resy.com-venue-details",
        })
        resp.raise_for_status()
        return resp.json()

    async def get_reservations(self) -> list[dict]:
        resp = await self._client.get("/3/user/reservations")
        resp.raise_for_status()
        return resp.json().get("reservations", [])
