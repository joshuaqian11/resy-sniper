import json
import logging
from urllib.parse import urlencode
from playwright.async_api import async_playwright, APIRequestContext
from typing import Optional

logger = logging.getLogger(__name__)

class ResyClient:
    BASE_URL = "https://api.resy.com"

    def __init__(self, api_key: str, email: str = "", password: str = "", cookies: str = ""):
        self.api_key = api_key
        self.email = email
        self.password = password
        self.cookies = cookies
        self.auth_token: str = ""
        self.payment_method_id: int = 0
        self._playwright = None
        self._browser = None
        self._context = None
        self._request: Optional[APIRequestContext] = None

    def _base_headers(self) -> dict:
        """Headers that mimic a real Chrome browser session on resy.com."""
        headers = {
            "authorization": f'ResyAPI api_key="{self.api_key}"',
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "accept-encoding": "gzip, deflate, br",
            "cache-control": "no-cache",
            "origin": "https://resy.com",
            "referer": "https://resy.com/",
            "x-origin": "https://resy.com",
            "host": "api.resy.com",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "connection": "keep-alive",
        }
        if self.auth_token:
            headers["x-resy-auth-token"] = self.auth_token
            headers["x-resy-universal-auth"] = self.auth_token
        return headers

    async def login(self) -> None:
        """Authenticate with Resy email/password and store the fresh auth token."""
        if not self.email or not self.password:
            raise RuntimeError("Resy email and password are required for auto-login")
        resp = await self._request.post(
            f"{self.BASE_URL}/3/auth/password",
            data=urlencode({"email": self.email, "password": self.password}),
            headers={
                "authorization": f'ResyAPI api_key="{self.api_key}"',
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://resy.com",
                "referer": "https://resy.com/",
                "host": "api.resy.com",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            },
        )
        if not resp.ok:
            raise RuntimeError(f"Login failed {resp.status}: {(await resp.text())[:200]}")
        data = await resp.json()
        token = data.get("legacy_token") or data.get("token")
        if not token:
            raise RuntimeError(f"Login response missing token")
        self.auth_token = token
        self.payment_method_id = data.get("payment_method_id") or 0
        logger.info(f"Resy login successful — auth token refreshed, payment_method_id={self.payment_method_id}")

    async def connect(self, venue_id: str | None = None, date: str | None = None, party_size: int = 2):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context()
        self._request = self._context.request

        if not self.auth_token:
            await self.login()

        # Pre-warm connection with real target data (uses GET like the live site)
        if venue_id and date:
            try:
                params = urlencode({
                    "lat": 0, "long": 0, "day": date,
                    "party_size": party_size, "venue_id": venue_id,
                })
                await self._request.get(
                    f"{self.BASE_URL}/4/find?{params}",
                    headers=self._base_headers(),
                )
            except Exception:
                pass

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._request = self._context = self._browser = self._playwright = None

    async def _get(self, path: str, params: dict) -> dict:
        """GET with automatic token refresh on 401."""
        headers = self._base_headers()
        url = f"{self.BASE_URL}{path}?{urlencode(params)}"
        resp = await self._request.get(url, headers=headers)
        if resp.status == 401 and self.email and self.password:
            logger.info("Got 401 — refreshing Resy auth token")
            await self.login()
            headers = self._base_headers()
            resp = await self._request.get(url, headers=headers)
        if not resp.ok:
            body = await resp.text()
            logger.warning(f"GET {path} got {resp.status}: {body[:500]}")
            raise Exception(f"HTTP {resp.status} from {path}: {body[:200]}")
        return await resp.json()

    async def _post_form(self, path: str, payload: dict, headers: dict | None = None) -> dict:
        """POST with form-encoded body and automatic token refresh on 401."""
        hdrs = headers or self._base_headers()
        hdrs["content-type"] = "application/x-www-form-urlencoded"
        body = urlencode(payload)
        resp = await self._request.post(
            f"{self.BASE_URL}{path}",
            data=body,
            headers=hdrs,
        )
        if resp.status == 401 and self.email and self.password:
            logger.info("Got 401 — refreshing Resy auth token")
            await self.login()
            hdrs = headers or self._base_headers()
            hdrs["content-type"] = "application/x-www-form-urlencoded"
            resp = await self._request.post(
                f"{self.BASE_URL}{path}",
                data=body,
                headers=hdrs,
            )
        if not resp.ok:
            body = await resp.text()
            logger.warning(f"POST {path} got {resp.status}: {body[:500]}")
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
        params = {
            "config_id": config_id,
            "day": date,
            "party_size": party_size,
        }
        if self.auth_token:
            params["x-resy-auth-token"] = self.auth_token
        data = await self._get("/3/details", params)
        logger.info(f"Details response keys: {list(data.keys())}")
        token = data["book_token"]["value"]
        logger.info(f"Got book token: {token[:20]}... expires={data['book_token'].get('date_expires')}")
        return token

    async def book(self, book_token: str) -> dict:
        payload = {
            "book_token": book_token,
            "struct_payment_method": json.dumps({"id": self.payment_method_id}),
            "source_id": "resy.com-venue-details",
        }
        # Booking goes through the widgets subdomain in real browser flow
        book_headers = self._base_headers()
        book_headers["origin"] = "https://widgets.resy.com"
        book_headers["referer"] = "https://widgets.resy.com/"
        book_headers["x-origin"] = "https://widgets.resy.com"
        logger.info(f"Booking with payment_method_id={self.payment_method_id}")
        return await self._post_form("/3/book", payload, headers=book_headers)

    async def get_reservations(self) -> list[dict]:
        resp = await self._request.get(
            f"{self.BASE_URL}/3/user/reservations",
            headers=self._base_headers(),
        )
        if not resp.ok:
            raise Exception(f"HTTP {resp.status} from /3/user/reservations")
        return (await resp.json()).get("reservations", [])
