import logging
import httpx
from typing import Optional
from http.cookies import SimpleCookie

logger = logging.getLogger(__name__)

BASE_URL = "https://api.resy.com"


class ResyClient:
    def __init__(self, api_key: str, email: str = "", password: str = "", cookies: str = ""):
        self.api_key = api_key
        self.email = email
        self.password = password
        self.cookies = cookies
        self.auth_token: Optional[str] = None
        self.payment_method_id: Optional[int] = None
        self._client: Optional[httpx.AsyncClient] = None

    def _headers(self) -> dict:
        headers = {
            "Authorization": f'ResyKey api_key="{self.api_key}"',
            "X-Resy-Auth-Token": self.auth_token or "",
            "Origin": "https://widgets.resy.com",
            "User-Agent": "Mozilla/5.0",
        }
        return headers

    async def _login(self):
        resp = await self._client.post(
            f"{BASE_URL}/3/auth/password",
            data={"email": self.email, "password": self.password},
            headers={"Authorization": f'ResyKey api_key="{self.api_key}"'},
        )
        resp.raise_for_status()
        data = resp.json()
        self.auth_token = data.get("token") or data.get("legacy_token")
        self.payment_method_id = data.get("payment_method_id")
        if not self.auth_token:
            raise RuntimeError("Login failed: no auth token in response")
        logger.info("Resy login successful")

    def _parse_cookies(self):
        if not self.cookies:
            return
        cookie = SimpleCookie()
        cookie.load(self.cookies)
        if "resy_auth_token" in cookie:
            self.auth_token = cookie["resy_auth_token"].value

    async def connect(self, venue_id: str = None, date: str = None, party_size: int = 2):
        self._client = httpx.AsyncClient(timeout=10.0)
        self._parse_cookies()
        if not self.auth_token and self.email and self.password:
            await self._login()
        if venue_id and date:
            await self.find_slots(venue_id, date, party_size)

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def find_slots(self, venue_id: str, date: str, party_size: int) -> list[dict]:
        resp = await self._client.get(
            f"{BASE_URL}/4/find",
            params={
                "lat": 0,
                "long": 0,
                "day": date,
                "party_size": party_size,
                "venue_id": venue_id,
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        venues = resp.json().get("results", {}).get("venues", [])
        if not venues:
            return []
        return venues[0].get("slots", [])

    async def get_book_token(self, config_id: str, date: str, party_size: int) -> str:
        resp = await self._client.get(
            f"{BASE_URL}/3/details",
            params={
                "config_id": config_id,
                "day": date,
                "party_size": party_size,
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()["book_token"]["value"]

    async def book(self, book_token: str) -> dict:
        resp = await self._client.post(
            f"{BASE_URL}/3/book",
            data={
                "book_token": book_token,
                "struct_payment_method": f'{{"id": {self.payment_method_id or 0}}}',
                "source_id": "resy.com-venue-details",
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def get_reservations(self) -> list[dict]:
        resp = await self._client.get(
            f"{BASE_URL}/3/user/reservations",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json().get("reservations", [])
