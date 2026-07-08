import asyncio, json, os
from urllib.parse import urlencode
from playwright.async_api import async_playwright
from dotenv import load_dotenv
load_dotenv()

async def test():
    api_key = os.environ.get("RESY_API_KEY", "")
    email = os.environ.get("RESY_EMAIL", "")
    password = os.environ.get("RESY_PASSWORD", "")
    print("API key loaded:", bool(api_key))

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        req = context.request

        # Login
        r = await req.post(
            "https://api.resy.com/3/auth/password",
            data=urlencode({"email": email, "password": password}),
            headers={
                "authorization": f'ResyAPI api_key="{api_key}"',
                "content-type": "application/x-www-form-urlencoded",
                "origin": "https://resy.com",
                "referer": "https://resy.com/",
                "host": "api.resy.com",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            },
        )
        print("Login status:", r.status)
        if not r.ok:
            print("Login failed:", await r.text())
            return
        data = await r.json()
        token = data.get("legacy_token") or data.get("token")

        headers = {
            "authorization": f'ResyAPI api_key="{api_key}"',
            "x-resy-auth-token": token,
            "x-resy-universal-auth": token,
            "accept": "application/json, text/plain, */*",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "en-US,en;q=0.9",
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

        # Test Uchiban across several dates (using GET with query params)
        tests = [
            ("Uchiban 06-11", "2026-06-11", 96061),
            ("Uchiban 06-12", "2026-06-12", 96061),
            ("Uchiban 06-15", "2026-06-15", 96061),
            ("Uchiban 06-17", "2026-06-17", 96061),
            ("Uchiban 06-20", "2026-06-20", 96061),
        ]
        for label, day, venue_id in tests:
            params = urlencode({"lat": 0, "long": 0, "day": day, "party_size": 2, "venue_id": venue_id})
            r2 = await req.get(
                f"https://api.resy.com/4/find?{params}",
                headers=headers,
            )
            print(f"[{label}] status={r2.status} body={(await r2.text())[:200]}")

        await context.close()
        await browser.close()

asyncio.run(test())
