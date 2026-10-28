import json
import logging
from urllib.parse import urlencode
from playwright.async_api import async_playwright
from typing import Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://api.resy.com"
# Resy returns 419 (not 401) for an expired token
AUTH_ERROR_STATUSES = (401, 419)


class ResyClient:
    def __init__(self, api_key: str, auth_token: str = "", email: str = "", password: str = "", cookies: str = ""):
        self.api_key = api_key
        self.email = email
        self.password = password
        self.cookies = cookies
        self.auth_token: Optional[str] = auth_token or None
        self.payment_method_id: int = 0
        self._playwright = None
        self._browser = None
        self._context = None
        self._request = None

    def _headers(self, overrides: dict = None) -> dict:
        headers = {
            "authorization": f'ResyAPI api_key="{self.api_key}"',
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "no-cache",
            "origin": "https://resy.com",
            "referer": "https://resy.com/",
            "x-origin": "https://resy.com",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
        if self.auth_token:
            headers["x-resy-auth-token"] = self.auth_token
            headers["x-resy-universal-auth"] = self.auth_token
        if overrides:
            headers.update(overrides)
        return headers

    def _can_login(self) -> bool:
        return bool(self.email and self.password)

    async def _login(self):
        resp = await self._request.post(
            f"{BASE_URL}/3/auth/password",
            data=urlencode({"email": self.email, "password": self.password}),
            headers={
                "authorization": f'ResyAPI api_key="{self.api_key}"',
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://resy.com",
                "referer": "https://resy.com/",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            },
        )
        if not resp.ok:
            raise RuntimeError(f"Login failed {resp.status}: {(await resp.text())[:200]}")
        data = await resp.json()
        self.auth_token = data.get("legacy_token") or data.get("token")
        self.payment_method_id = data.get("payment_method_id") or 0
        if not self.auth_token:
            raise RuntimeError("Login failed: no auth token in response")
        logger.info("Resy login successful")

    async def connect(self, venue_id: str = None, date: str = None, party_size: int = 2):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context()
        self._request = self._context.request

        # Always log in fresh when credentials exist — stored tokens expire.
        if self._can_login():
            await self._login()
        if venue_id and date:
            await self.find_slots(venue_id, date, party_size)

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def _get(self, path: str, params: dict) -> dict:
        url = f"{BASE_URL}{path}?{urlencode(params)}"
        resp = await self._request.get(url, headers=self._headers())
        if resp.status in AUTH_ERROR_STATUSES and self._can_login():
            logger.info(f"Got {resp.status} — refreshing auth token")
            await self._login()
            resp = await self._request.get(url, headers=self._headers())
        if not resp.ok:
            body = await resp.text()
            raise Exception(f"HTTP {resp.status} from {path}: {body[:200]}")
        return await resp.json()

    async def _post_form(self, path: str, payload: dict, header_overrides: dict = None) -> dict:
        async def post():
            hdrs = self._headers(header_overrides)
            hdrs["content-type"] = "application/x-www-form-urlencoded"
            return await self._request.post(
                f"{BASE_URL}{path}",
                data=urlencode(payload),
                headers=hdrs,
            )

        resp = await post()
        if resp.status in AUTH_ERROR_STATUSES and self._can_login():
            logger.info(f"Got {resp.status} — refreshing auth token")
            await self._login()
            resp = await post()
        if not resp.ok:
            body = await resp.text()
            raise Exception(f"HTTP {resp.status} from {path}: {body[:200]}")
        return await resp.json()

    async def find_slots(self, venue_id: str, date: str, party_size: int) -> list[dict]:
        data = await self._get("/4/find", {
            "lat": 0, "long": 0, "day": date,
            "party_size": party_size, "venue_id": venue_id,
        })
        venues = data.get("results", {}).get("venues", [])
        if not venues:
            return []
        return venues[0].get("slots", [])

    async def get_book_token(self, config_id: str, date: str, party_size: int) -> str:
        data = await self._get("/3/details", {
            "config_id": config_id,
            "day": date,
            "party_size": party_size,
        })
        return data["book_token"]["value"]

    async def book(self, book_token: str) -> dict:
        book_headers = {
            "origin": "https://widgets.resy.com",
            "referer": "https://widgets.resy.com/",
            "x-origin": "https://widgets.resy.com",
        }
        return await self._post_form("/3/book", {
            "book_token": book_token,
            "struct_payment_method": json.dumps({"id": self.payment_method_id}),
            "source_id": "resy.com-venue-details",
        }, header_overrides=book_headers)

    async def get_reservations(self) -> list[dict]:
        resp = await self._request.get(
            f"{BASE_URL}/3/user/reservations",
            headers=self._headers(),
        )
        if not resp.ok:
            raise Exception(f"HTTP {resp.status} from /3/user/reservations")
        return (await resp.json()).get("reservations", [])
