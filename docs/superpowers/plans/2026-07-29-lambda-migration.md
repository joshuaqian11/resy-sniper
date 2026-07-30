# Lambda Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the Resy snipe bot from EC2+SQLite to a fully serverless architecture using Lambda+DynamoDB+EventBridge, with the dashboard running locally.

**Architecture:** DynamoDB replaces SQLite for persistence. EventBridge scheduled rules invoke a Lambda function (instead of starting an EC2 instance) 2 minutes before each snipe. The FastAPI dashboard runs locally and talks directly to DynamoDB/EventBridge. Playwright is replaced with httpx for Lambda compatibility.

**Tech Stack:** Python 3.12, FastAPI, httpx (async), boto3, DynamoDB, Lambda, EventBridge, React 18, Vite, Tailwind CSS

---

## File Map

```
resy-bot/
  backend/
    database.py          # REWRITE: SQLite → DynamoDB (boto3)
    config.py            # MODIFY: remove Twilio fields
    auth.py              # UNCHANGED
    resy.py              # REWRITE: Playwright → httpx
    snipe.py             # MODIFY: preferred_time + window logic, remove sms
    aws.py               # MODIFY: Lambda target, remove EC2 methods
    lambda_handler.py    # NEW: Lambda entry point
    main.py              # MODIFY: remove scheduler/EC2, add complete_past_targets
    requirements.txt     # MODIFY: swap deps
    routers/
      __init__.py        # UNCHANGED
      targets.py         # MODIFY: new fields, Lambda ARN, string IDs
      settings.py        # MODIFY: remove Twilio fields
      reservations.py    # UNCHANGED
    tests/
      conftest.py        # REWRITE: DynamoDB fixtures (moto)
      test_database.py   # REWRITE: DynamoDB tests
      test_config.py     # MODIFY: remove Twilio fields
      test_aws.py        # MODIFY: Lambda target assertions
      test_snipe.py      # MODIFY: new filter logic tests
      test_targets.py    # MODIFY: string IDs, new fields
      test_settings.py   # MODIFY: remove Twilio fields
      test_lambda.py     # NEW: Lambda handler tests
      test_resy.py       # REWRITE: httpx mocking (respx)
      test_auth.py       # UNCHANGED
  frontend/
    src/
      api.ts             # MODIFY: new types, string IDs, completed status
      pages/
        TargetsPage.tsx  # MODIFY: new form fields, completed status display
        SettingsPage.tsx # MODIFY: remove Twilio section
      components/
        StatusBadge.tsx  # MODIFY: add completed color
  deploy/
    deploy.sh            # NEW: Lambda zip packaging script
    IAM_SETUP.md         # REWRITE: Lambda + local user IAM setup

  FILES TO DELETE:
    backend/scheduler.py
    backend/sms.py
    backend/tests/test_scheduler.py
    backend/tests/test_sms.py
    deploy/setup.sh
    deploy/resy-bot.service
    deploy/nginx.conf
```

---

## Task 1: Update Dependencies

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Update requirements.txt**

Replace the contents of `backend/requirements.txt` with:

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
httpx==0.27.2
boto3==1.35.40
python-dotenv==1.0.1
```

Remove: `playwright`, `apscheduler`, `twilio`, `aiosqlite`

- [ ] **Step 2: Install updated dependencies**

```bash
cd backend
pip install -r requirements.txt
```

Expected: All packages install successfully.

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: update deps for Lambda migration — remove playwright, apscheduler, twilio, aiosqlite"
```

---

## Task 2: Database Layer (DynamoDB)

**Files:**
- Rewrite: `backend/database.py`
- Rewrite: `backend/tests/conftest.py`
- Rewrite: `backend/tests/test_database.py`

- [ ] **Step 1: Write failing tests**

`backend/tests/conftest.py`:
```python
import os
import pytest
import boto3
from moto import mock_aws
from database import Database

REGION = "us-east-1"

@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")

@pytest.fixture
def dynamodb_tables(aws_env):
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)
        client.create_table(
            TableName="resy-bot-targets",
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName="resy-bot-config",
            KeySchema=[{"AttributeName": "key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield

@pytest.fixture
def db(dynamodb_tables):
    return Database(region=REGION)
```

`backend/tests/test_database.py`:
```python
import pytest
from database import Database


def test_insert_and_fetch_target(db):
    target_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00Z",
        "preferred_time": "19:00",
        "window_start": "18:00",
        "window_end": "21:00",
    })
    assert isinstance(target_id, str)
    targets = db.get_all_targets()
    assert len(targets) == 1
    assert targets[0]["venue_name"] == "Carbone"
    assert targets[0]["status"] == "pending"
    assert targets[0]["party_size"] == 2


def test_get_target_by_id(db):
    target_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00Z",
    })
    target = db.get_target(target_id)
    assert target is not None
    assert target["venue_name"] == "Carbone"


def test_get_target_missing_returns_none(db):
    assert db.get_target("nonexistent-id") is None


def test_update_target_status(db):
    target_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00Z",
    })
    db.update_target_status(target_id, "sniping")
    target = db.get_target(target_id)
    assert target["status"] == "sniping"


def test_update_target_booked(db):
    target_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00Z",
    })
    db.update_target_booked(target_id, {"resy_token": "abc123"})
    target = db.get_target(target_id)
    assert target["status"] == "booked"
    assert '"resy_token"' in target["reservation_details"]
    assert target["booked_at"] is not None


def test_delete_pending_target(db):
    target_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00Z",
    })
    assert db.delete_target_if_pending(target_id) is True
    assert db.get_target(target_id) is None


def test_delete_non_pending_target_fails(db):
    target_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2026-05-16T09:00:00Z",
    })
    db.update_target_status(target_id, "sniping")
    assert db.delete_target_if_pending(target_id) is False
    assert db.get_target(target_id) is not None


def test_complete_past_targets(db):
    # Insert a booked target with past date
    past_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2020-01-01",
        "party_size": 2,
        "opening_time": "2019-12-02T09:00:00Z",
    })
    db.update_target_status(past_id, "booked")

    # Insert a pending target with future date
    future_id = db.insert_target({
        "venue_id": "456",
        "venue_name": "Le Bernardin",
        "date": "2099-06-15",
        "party_size": 4,
        "opening_time": "2099-05-16T09:00:00Z",
    })

    db.complete_past_targets()

    past = db.get_target(past_id)
    assert past["status"] == "completed"

    future = db.get_target(future_id)
    assert future["status"] == "pending"


def test_config_set_and_get(db):
    db.set_config("resy_api_key", "my-key")
    assert db.get_config("resy_api_key") == "my-key"


def test_config_missing_returns_none(db):
    assert db.get_config("nonexistent") is None


def test_config_get_all(db):
    db.set_config("resy_api_key", "key1")
    db.set_config("resy_email", "test@test.com")
    config = db.get_all_config()
    assert config["resy_api_key"] == "key1"
    assert config["resy_email"] == "test@test.com"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_database.py -v
```

Expected: Failures due to changed `Database` interface.

- [ ] **Step 3: Implement database.py**

`backend/database.py`:
```python
import json
import uuid
import boto3
from datetime import datetime, timezone
from typing import Optional


class Database:
    def __init__(self, region: str = "us-east-1"):
        self._dynamodb = boto3.resource("dynamodb", region_name=region)
        self._targets = self._dynamodb.Table("resy-bot-targets")
        self._config = self._dynamodb.Table("resy-bot-config")

    def insert_target(self, t: dict) -> str:
        target_id = str(uuid.uuid4())
        item = {
            "id": target_id,
            "venue_id": t["venue_id"],
            "venue_name": t["venue_name"],
            "date": t["date"],
            "party_size": t["party_size"],
            "opening_time": t["opening_time"],
            "status": "pending",
        }
        for key in ("preferred_time", "window_start", "window_end"):
            if t.get(key):
                item[key] = t[key]
        self._targets.put_item(Item=item)
        return target_id

    def get_all_targets(self) -> list[dict]:
        response = self._targets.scan()
        items = response.get("Items", [])
        for item in items:
            if "party_size" in item:
                item["party_size"] = int(item["party_size"])
        return sorted(items, key=lambda x: x.get("opening_time", ""))

    def get_target(self, target_id: str) -> Optional[dict]:
        response = self._targets.get_item(Key={"id": target_id})
        item = response.get("Item")
        if item and "party_size" in item:
            item["party_size"] = int(item["party_size"])
        return item

    def update_target_status(self, target_id: str, status: str):
        self._targets.update_item(
            Key={"id": target_id},
            UpdateExpression="SET #s = :status",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":status": status},
        )

    def update_target_booked(self, target_id: str, reservation_details: dict):
        now = datetime.now(timezone.utc).isoformat()
        self._targets.update_item(
            Key={"id": target_id},
            UpdateExpression="SET #s = :status, booked_at = :booked_at, reservation_details = :details",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": "booked",
                ":booked_at": now,
                ":details": json.dumps(reservation_details),
            },
        )

    def delete_target_if_pending(self, target_id: str) -> bool:
        try:
            self._targets.delete_item(
                Key={"id": target_id},
                ConditionExpression="#s = :pending",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":pending": "pending"},
            )
            return True
        except self._dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            return False

    def complete_past_targets(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        response = self._targets.scan(
            FilterExpression="#s IN (:booked, :failed) AND #d < :today",
            ExpressionAttributeNames={"#s": "status", "#d": "date"},
            ExpressionAttributeValues={
                ":booked": "booked",
                ":failed": "failed",
                ":today": today,
            },
        )
        for item in response.get("Items", []):
            self.update_target_status(item["id"], "completed")

    def set_config(self, key: str, value: str):
        self._config.put_item(Item={"key": key, "value": value})

    def get_config(self, key: str) -> Optional[str]:
        response = self._config.get_item(Key={"key": key})
        item = response.get("Item")
        return item["value"] if item else None

    def get_all_config(self) -> dict[str, str]:
        response = self._config.scan()
        return {item["key"]: item["value"] for item in response.get("Items", [])}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
python -m pytest tests/test_database.py -v
```

Expected: All 12 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/database.py backend/tests/conftest.py backend/tests/test_database.py
git commit -m "feat: rewrite database layer from SQLite to DynamoDB"
```

---

## Task 3: Config (Remove Twilio)

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/tests/test_config.py`

- [ ] **Step 1: Write failing tests**

`backend/tests/test_config.py`:
```python
import pytest
from moto import mock_aws
from config import Settings, load_settings, save_settings


@mock_aws
def test_load_settings_returns_defaults_when_empty(db):
    settings = load_settings(db)
    assert settings.resy_api_key == ""
    assert settings.resy_email == ""
    assert settings.resy_password == ""
    assert settings.resy_cookies == ""


@mock_aws
def test_save_and_load_settings(db):
    s = Settings(
        resy_api_key="key123",
        resy_email="test@test.com",
        resy_password="pass456",
        resy_cookies="cookie-data",
    )
    save_settings(db, s)
    loaded = load_settings(db)
    assert loaded.resy_api_key == "key123"
    assert loaded.resy_email == "test@test.com"
    assert loaded.resy_password == "pass456"
    assert loaded.resy_cookies == "cookie-data"
```

- [ ] **Step 2: Implement config.py**

`backend/config.py`:
```python
from dataclasses import dataclass, fields
from database import Database

CONFIG_KEYS = [
    "resy_api_key", "resy_email", "resy_password", "resy_cookies",
]


@dataclass
class Settings:
    resy_api_key: str = ""
    resy_email: str = ""
    resy_password: str = ""
    resy_cookies: str = ""


def load_settings(db: Database) -> Settings:
    raw = db.get_all_config()
    return Settings(**{k: raw.get(k, "") for k in CONFIG_KEYS})


def save_settings(db: Database, settings: Settings):
    for f in fields(settings):
        db.set_config(f.name, getattr(settings, f.name) or "")
```

- [ ] **Step 3: Run tests**

```bash
cd backend
python -m pytest tests/test_config.py -v
```

Expected: All 2 tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/config.py backend/tests/test_config.py
git commit -m "feat: update config — remove Twilio fields, sync interface"
```

---

## Task 4: Resy Client (Playwright → httpx)

**Files:**
- Rewrite: `backend/resy.py`
- Rewrite: `backend/tests/test_resy.py`

The current `resy.py` uses Playwright (browser-based HTTP). Lambda can't run Playwright (too large, needs Chromium). Rewrite to use httpx. Same API methods, same Resy endpoints.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_resy.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_resy.py -v
```

Expected: Failures due to changed `ResyClient` implementation.

- [ ] **Step 3: Implement resy.py**

`backend/resy.py`:
```python
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
```

- [ ] **Step 4: Run tests**

```bash
cd backend
python -m pytest tests/test_resy.py -v
```

Expected: All 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/resy.py backend/tests/test_resy.py
git commit -m "feat: rewrite Resy client from Playwright to httpx for Lambda compatibility"
```

---

## Task 5: Snipe Logic (preferred_time + window)

**Files:**
- Modify: `backend/snipe.py`
- Modify: `backend/tests/test_snipe.py`

Replace `preferred_start`/`preferred_end` with `preferred_time` (soft preference) + `window_start`/`window_end` (hard filter). Remove SMS dependency.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_snipe.py`:
```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from snipe import run_snipe, filter_slots, pick_best_slot


# --- filter_slots tests ---

def test_filter_slots_no_window():
    slots = [
        {"date": {"start": "2026-06-15 19:00:00"}, "config": {"token": "tok1"}},
        {"date": {"start": "2026-06-15 21:30:00"}, "config": {"token": "tok2"}},
    ]
    assert filter_slots(slots, None, None) == slots


def test_filter_slots_within_window():
    slots = [
        {"date": {"start": "2026-06-15 17:00:00"}, "config": {"token": "too-early"}},
        {"date": {"start": "2026-06-15 19:00:00"}, "config": {"token": "ok"}},
        {"date": {"start": "2026-06-15 22:00:00"}, "config": {"token": "too-late"}},
    ]
    result = filter_slots(slots, "18:00", "21:00")
    assert len(result) == 1
    assert result[0]["config"]["token"] == "ok"


def test_filter_slots_window_start_only():
    slots = [
        {"date": {"start": "2026-06-15 17:00:00"}, "config": {"token": "early"}},
        {"date": {"start": "2026-06-15 19:00:00"}, "config": {"token": "ok"}},
    ]
    result = filter_slots(slots, "18:00", None)
    assert len(result) == 1
    assert result[0]["config"]["token"] == "ok"


def test_filter_slots_empty_list():
    assert filter_slots([], "18:00", "21:00") == []


# --- pick_best_slot tests ---

def test_pick_best_slot_no_preference():
    slots = [
        {"date": {"start": "2026-06-15 19:00:00"}, "config": {"token": "first"}},
        {"date": {"start": "2026-06-15 20:00:00"}, "config": {"token": "second"}},
    ]
    result = pick_best_slot(slots, None)
    assert result["config"]["token"] == "first"


def test_pick_best_slot_with_preference():
    slots = [
        {"date": {"start": "2026-06-15 18:00:00"}, "config": {"token": "6pm"}},
        {"date": {"start": "2026-06-15 19:30:00"}, "config": {"token": "730pm"}},
        {"date": {"start": "2026-06-15 21:00:00"}, "config": {"token": "9pm"}},
    ]
    result = pick_best_slot(slots, "19:00")
    assert result["config"]["token"] == "730pm"


def test_pick_best_slot_empty_returns_none():
    assert pick_best_slot([], "19:00") is None


# --- run_snipe tests ---

def make_target(**overrides):
    base = {
        "id": "test-uuid-1",
        "venue_id": "venue1",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
    }
    base.update(overrides)
    return base


def make_slot(token="tok1", time="2026-06-15 19:00:00"):
    return {"date": {"start": time}, "config": {"token": token}}


@pytest.mark.asyncio
async def test_run_snipe_books_on_first_slot():
    target = make_target()
    mock_db = MagicMock()
    mock_resy = AsyncMock()

    slot = make_slot()
    mock_resy.find_slots = AsyncMock(side_effect=[[slot], [], []])
    mock_resy.get_book_token = AsyncMock(return_value="book-tok-xyz")
    mock_resy.book = AsyncMock(return_value={"resy_token": "res-abc"})

    await run_snipe(target, mock_resy, mock_db)

    mock_resy.book.assert_called_once_with("book-tok-xyz")
    mock_db.update_target_booked.assert_called_once_with("test-uuid-1", {"resy_token": "res-abc"})


@pytest.mark.asyncio
async def test_run_snipe_retries_book_on_timeout():
    target = make_target()
    mock_db = MagicMock()
    mock_resy = AsyncMock()

    slot = make_slot()
    mock_resy.find_slots = AsyncMock(return_value=[slot])
    mock_resy.get_book_token = AsyncMock(return_value="book-tok-xyz")
    mock_resy.book = AsyncMock(side_effect=[
        httpx.TimeoutException("timeout"),
        {"resy_token": "res-abc"},
    ])

    await run_snipe(target, mock_resy, mock_db)

    assert mock_resy.book.call_count == 2
    mock_db.update_target_booked.assert_called_once()


@pytest.mark.asyncio
async def test_run_snipe_marks_failed_when_no_slots():
    target = make_target()
    mock_db = MagicMock()
    mock_resy = AsyncMock()
    mock_resy.find_slots = AsyncMock(return_value=[])

    with patch("snipe.PHASE1_DURATION", 0.01), patch("snipe.PHASE2_DURATION", 0.01):
        await run_snipe(target, mock_resy, mock_db)

    mock_db.update_target_status.assert_any_call("test-uuid-1", "failed")


@pytest.mark.asyncio
async def test_run_snipe_fails_on_terminal_book_error():
    target = make_target()
    mock_db = MagicMock()
    mock_resy = AsyncMock()

    slot = make_slot()
    mock_resy.find_slots = AsyncMock(return_value=[slot])
    mock_resy.get_book_token = AsyncMock(return_value="book-tok-xyz")
    mock_resy.book = AsyncMock(side_effect=httpx.HTTPStatusError(
        "422", request=MagicMock(), response=MagicMock(status_code=422)
    ))

    await run_snipe(target, mock_resy, mock_db)

    mock_db.update_target_status.assert_any_call("test-uuid-1", "failed")


@pytest.mark.asyncio
async def test_run_snipe_uses_window_filter():
    target = make_target(window_start="18:00", window_end="20:00")
    mock_db = MagicMock()
    mock_resy = AsyncMock()

    early_slot = make_slot(token="too-early", time="2026-06-15 17:00:00")
    good_slot = make_slot(token="good", time="2026-06-15 19:00:00")
    mock_resy.find_slots = AsyncMock(side_effect=[[early_slot, good_slot], []])
    mock_resy.get_book_token = AsyncMock(return_value="book-tok")
    mock_resy.book = AsyncMock(return_value={"resy_token": "res-abc"})

    await run_snipe(target, mock_resy, mock_db)

    mock_resy.get_book_token.assert_called_once_with("good", "2026-06-15", 2)


@pytest.mark.asyncio
async def test_run_snipe_picks_closest_to_preferred_time():
    target = make_target(preferred_time="19:30")
    mock_db = MagicMock()
    mock_resy = AsyncMock()

    slots = [
        make_slot(token="6pm", time="2026-06-15 18:00:00"),
        make_slot(token="730pm", time="2026-06-15 19:30:00"),
        make_slot(token="9pm", time="2026-06-15 21:00:00"),
    ]
    mock_resy.find_slots = AsyncMock(side_effect=[slots, []])
    mock_resy.get_book_token = AsyncMock(return_value="book-tok")
    mock_resy.book = AsyncMock(return_value={"resy_token": "res-abc"})

    await run_snipe(target, mock_resy, mock_db)

    mock_resy.get_book_token.assert_called_once_with("730pm", "2026-06-15", 2)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_snipe.py -v
```

Expected: `ImportError` for `pick_best_slot`, failures for new tests.

- [ ] **Step 3: Implement snipe.py**

`backend/snipe.py`:
```python
import asyncio
import logging

logger = logging.getLogger(__name__)

PHASE1_DURATION = 60.0
PHASE2_DURATION = 60.0
PHASE1_INTERVAL = 1.0
PHASE2_INTERVAL = 2.0


def _extract_time(slot: dict) -> str:
    """Extract HH:MM from slot date string like '2026-06-15 19:00:00'."""
    return slot["date"]["start"].split(" ")[1][:5]


def filter_slots(slots: list[dict], window_start: str | None, window_end: str | None) -> list[dict]:
    """Filter slots by hard time window boundaries."""
    if not window_start and not window_end:
        return slots
    result = []
    for slot in slots:
        slot_time = _extract_time(slot)
        if window_start and slot_time < window_start:
            continue
        if window_end and slot_time > window_end:
            continue
        result.append(slot)
    return result


def pick_best_slot(slots: list[dict], preferred_time: str | None) -> dict | None:
    """Pick the slot closest to preferred_time, or the first slot if no preference."""
    if not slots:
        return None
    if not preferred_time:
        return slots[0]
    return min(slots, key=lambda s: abs(
        _time_minutes(_extract_time(s)) - _time_minutes(preferred_time)
    ))


def _time_minutes(hhmm: str) -> int:
    """Convert HH:MM to minutes since midnight."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


async def _book_with_retry(resy_client, book_token: str) -> dict:
    while True:
        try:
            return await resy_client.book(book_token)
        except Exception as e:
            import httpx
            if isinstance(e, httpx.TimeoutException):
                logger.warning("Book request timed out — retrying with same token")
                continue
            raise


async def run_snipe(target: dict, resy_client, db) -> None:
    target_id = target["id"]
    venue_name = target.get("venue_name", "Unknown")
    venue_id = target["venue_id"]
    date = target["date"]
    party_size = target["party_size"]
    window_start = target.get("window_start")
    window_end = target.get("window_end")
    preferred_time = target.get("preferred_time")

    db.update_target_status(target_id, "sniping")
    logger.info(f"[{venue_name}] Snipe started")

    booking_in_flight = False
    booked = False

    async def attempt_booking(slot: dict):
        nonlocal booking_in_flight, booked
        if booking_in_flight or booked:
            return
        booking_in_flight = True
        try:
            config_id = slot["config"]["token"]
            book_token = await resy_client.get_book_token(config_id, date, party_size)
            result = await _book_with_retry(resy_client, book_token)
            booked = True
            db.update_target_booked(target_id, result)
            logger.info(f"[{venue_name}] Booked successfully")
        except Exception as e:
            logger.error(f"[{venue_name}] Booking failed: {e}")
            db.update_target_status(target_id, "failed")
        finally:
            if not booked:
                booking_in_flight = False

    loop = asyncio.get_event_loop()

    async def poll(interval: float, duration: float):
        deadline = loop.time() + duration
        while loop.time() < deadline and not booked:
            try:
                slots = await resy_client.find_slots(venue_id, date, party_size)
                matching = filter_slots(slots, window_start, window_end)
                best = pick_best_slot(matching, preferred_time)
                if best and not booking_in_flight and not booked:
                    asyncio.ensure_future(attempt_booking(best))
            except Exception as e:
                logger.warning(f"[{venue_name}] find_slots error: {e}")
            await asyncio.sleep(interval)

    await poll(PHASE1_INTERVAL, PHASE1_DURATION)
    if not booked:
        await poll(PHASE2_INTERVAL, PHASE2_DURATION)

    if not booked and not booking_in_flight:
        db.update_target_status(target_id, "failed")
        logger.warning(f"[{venue_name}] Snipe window expired with no booking")
```

- [ ] **Step 4: Run tests**

```bash
cd backend
python -m pytest tests/test_snipe.py -v
```

Expected: All 14 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/snipe.py backend/tests/test_snipe.py
git commit -m "feat: update snipe logic — preferred_time + window filter, remove SMS dependency"
```

---

## Task 6: AWS Client (Lambda Target)

**Files:**
- Modify: `backend/aws.py`
- Modify: `backend/tests/test_aws.py`

Remove EC2 methods (`stop_self`, `get_instance_id`). Update EventBridge target from SSM automation (start EC2) to Lambda invocation. Change pre-fire offset from 10 minutes to 2 minutes.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_aws.py`:
```python
import pytest
import boto3
from moto import mock_aws
from aws import AWSClient

REGION = "us-east-1"
LAMBDA_ARN = "arn:aws:lambda:us-east-1:123456789:function:resy-bot-snipe"


@pytest.fixture
def aws_client(aws_env):
    return AWSClient(region=REGION, lambda_arn=LAMBDA_ARN)


@mock_aws
def test_create_start_rule(aws_client):
    aws_client.create_start_rule(
        rule_name="resy-bot-target-abc",
        cron_expression="cron(58 8 15 8 ? 2026)",
        target_id="abc-uuid",
    )
    events = boto3.client("events", region_name=REGION)
    rules = events.list_rules(NamePrefix="resy-bot-target-abc")["Rules"]
    assert len(rules) == 1
    assert rules[0]["Name"] == "resy-bot-target-abc"
    assert rules[0]["State"] == "ENABLED"


@mock_aws
def test_create_start_rule_sets_lambda_target(aws_client):
    aws_client.create_start_rule(
        rule_name="resy-bot-target-abc",
        cron_expression="cron(58 8 15 8 ? 2026)",
        target_id="abc-uuid",
    )
    events = boto3.client("events", region_name=REGION)
    targets = events.list_targets_by_rule(Rule="resy-bot-target-abc")["Targets"]
    assert len(targets) == 1
    assert targets[0]["Arn"] == LAMBDA_ARN
    assert '"target_id": "abc-uuid"' in targets[0]["Input"]


@mock_aws
def test_delete_rule(aws_client):
    events = boto3.client("events", region_name=REGION)
    events.put_rule(
        Name="resy-bot-target-99",
        ScheduleExpression="cron(0 9 15 6 ? 2026)",
        State="ENABLED",
    )
    aws_client.delete_rule("resy-bot-target-99")
    rules = events.list_rules(NamePrefix="resy-bot-target-99")["Rules"]
    assert len(rules) == 0


@mock_aws
def test_delete_rule_nonexistent_does_not_raise(aws_client):
    aws_client.delete_rule("does-not-exist")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_aws.py -v
```

Expected: Failures due to changed `AWSClient` constructor.

- [ ] **Step 3: Implement aws.py**

`backend/aws.py`:
```python
import json
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class AWSClient:
    def __init__(self, region: str, lambda_arn: str):
        self.region = region
        self.lambda_arn = lambda_arn
        self._events = boto3.client("events", region_name=region)

    def create_start_rule(self, rule_name: str, cron_expression: str, target_id: str):
        """Create an EventBridge rule that invokes the snipe Lambda on a schedule."""
        self._events.put_rule(
            Name=rule_name,
            ScheduleExpression=cron_expression,
            State="ENABLED",
            Description=f"Resy bot snipe trigger for target {target_id}",
        )
        self._events.put_targets(
            Rule=rule_name,
            Targets=[{
                "Id": "invoke-snipe-lambda",
                "Arn": self.lambda_arn,
                "Input": json.dumps({"target_id": target_id}),
            }],
        )

    def delete_rule(self, rule_name: str):
        """Remove targets then delete the EventBridge rule. No-op if rule doesn't exist."""
        try:
            self._events.remove_targets(Rule=rule_name, Ids=["invoke-snipe-lambda"])
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code not in ("ResourceNotFoundException", "ValidationException"):
                logger.error(f"Failed to remove targets for rule {rule_name}: {e}")
        try:
            self._events.delete_rule(Name=rule_name)
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                logger.error(f"Failed to delete rule {rule_name}: {e}")
```

- [ ] **Step 4: Run tests**

```bash
cd backend
python -m pytest tests/test_aws.py -v
```

Expected: All 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/aws.py backend/tests/test_aws.py
git commit -m "feat: update AWS client — Lambda target for EventBridge, remove EC2 methods"
```

---

## Task 7: Lambda Handler

**Files:**
- Create: `backend/lambda_handler.py`
- Create: `backend/tests/test_lambda.py`

- [ ] **Step 1: Write failing tests**

`backend/tests/test_lambda.py`:
```python
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
        mock_asyncio.run = lambda coro: __import__("asyncio").get_event_loop().run_until_complete(coro)
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


@mock_aws
def test_handler_returns_error_for_missing_target(db):
    with patch("lambda_handler.Database") as MockDB:
        mock_db = MagicMock()
        mock_db.get_target.return_value = None
        MockDB.return_value = mock_db

        result = handler(make_event("nonexistent"), None)
        assert result["statusCode"] == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_lambda.py -v
```

Expected: `ModuleNotFoundError: No module named 'lambda_handler'`

- [ ] **Step 3: Implement lambda_handler.py**

`backend/lambda_handler.py`:
```python
import asyncio
import logging
from datetime import datetime, timezone
from database import Database
from resy import ResyClient
from snipe import run_snipe

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def _run(target: dict, db: Database):
    config = db.get_all_config()
    resy_client = ResyClient(
        api_key=config.get("resy_api_key", ""),
        email=config.get("resy_email", ""),
        password=config.get("resy_password", ""),
        cookies=config.get("resy_cookies", ""),
    )
    try:
        await resy_client.connect(
            venue_id=target["venue_id"],
            date=target["date"],
            party_size=target["party_size"],
        )

        opening_time = datetime.fromisoformat(target["opening_time"])
        if opening_time.tzinfo is None:
            opening_time = opening_time.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        wait_seconds = (opening_time - now).total_seconds()
        if wait_seconds > 0:
            logger.info(f"Waiting {wait_seconds:.0f}s until opening time")
            await asyncio.sleep(wait_seconds)

        await run_snipe(target, resy_client, db)
    finally:
        await resy_client.close()


def handler(event, context):
    target_id = event.get("target_id")
    if not target_id:
        logger.error("No target_id in event")
        return {"statusCode": 400, "body": "Missing target_id"}

    db = Database()
    target = db.get_target(target_id)

    if not target:
        logger.error(f"Target {target_id} not found")
        return {"statusCode": 404, "body": "Target not found"}

    if target["status"] != "pending":
        logger.info(f"Target {target_id} status is {target['status']}, skipping")
        return {"statusCode": 200, "body": f"Skipped — status is {target['status']}"}

    logger.info(f"Starting snipe for target {target_id} ({target.get('venue_name')})")
    asyncio.run(_run(target, db))

    updated = db.get_target(target_id)
    status = updated["status"] if updated else "unknown"
    logger.info(f"Snipe complete for target {target_id} — status: {status}")
    return {"statusCode": 200, "body": f"Snipe complete — {status}"}
```

- [ ] **Step 4: Run tests**

```bash
cd backend
python -m pytest tests/test_lambda.py -v
```

Expected: All 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/lambda_handler.py backend/tests/test_lambda.py
git commit -m "feat: Lambda handler — entry point for EventBridge-triggered snipes"
```

---

## Task 8: Dashboard Backend (main.py + routers)

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/routers/targets.py`
- Modify: `backend/routers/settings.py`
- Modify: `backend/tests/test_targets.py`
- Modify: `backend/tests/test_settings.py`

- [ ] **Step 1: Write failing tests for targets**

`backend/tests/test_targets.py`:
```python
import os
import pytest
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from database import Database

os.environ["DASHBOARD_API_KEY"] = "test-key"


@pytest.fixture
def mock_aws_client():
    client = MagicMock()
    client.create_start_rule = MagicMock()
    client.delete_rule = MagicMock()
    return client


@pytest.fixture
def test_app(db, mock_aws_client):
    from main import create_app
    app = create_app(db=db, aws_client=mock_aws_client)
    return app, db, mock_aws_client


@pytest.mark.asyncio
async def test_list_targets_empty(test_app):
    app, db, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/targets", headers={"x-api-key": "test-key"})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_add_target(test_app):
    app, db, mock_aws_client = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/targets", headers={"x-api-key": "test-key"}, json={
            "venue_id": "123",
            "venue_name": "Carbone",
            "date": "2026-06-15",
            "party_size": 2,
            "opening_time": "2099-05-16T09:00:00Z",
            "preferred_time": "19:00",
            "window_start": "18:00",
            "window_end": "21:00",
        })
    assert resp.status_code == 201
    data = resp.json()
    assert data["venue_name"] == "Carbone"
    assert data["status"] == "pending"
    assert data["preferred_time"] == "19:00"
    assert data["window_start"] == "18:00"
    mock_aws_client.create_start_rule.assert_called_once()


@pytest.mark.asyncio
async def test_delete_pending_target(test_app):
    app, db, mock_aws_client = test_app
    target_id = db.insert_target({
        "venue_id": "123",
        "venue_name": "Carbone",
        "date": "2026-06-15",
        "party_size": 2,
        "opening_time": "2099-05-16T09:00:00Z",
    })
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"/api/targets/{target_id}", headers={"x-api-key": "test-key"})
    assert resp.status_code == 204
    mock_aws_client.delete_rule.assert_called_once()


@pytest.mark.asyncio
async def test_unauthorized_request_rejected(test_app):
    app, _, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/targets", headers={"x-api-key": "wrong"})
    assert resp.status_code == 401
```

- [ ] **Step 2: Write failing tests for settings**

`backend/tests/test_settings.py`:
```python
import os
import pytest
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from database import Database

os.environ["DASHBOARD_API_KEY"] = "test-key"


@pytest.fixture
def test_app(db):
    from main import create_app
    mock_aws_client = MagicMock()
    app = create_app(db=db, aws_client=mock_aws_client)
    return app, db


@pytest.mark.asyncio
async def test_get_settings_empty(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/settings", headers={"x-api-key": "test-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resy_api_key"] == ""
    assert "twilio_account_sid" not in data


@pytest.mark.asyncio
async def test_put_settings(test_app):
    app, db = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put("/api/settings", headers={"x-api-key": "test-key"}, json={
            "resy_api_key": "key123",
            "resy_email": "test@test.com",
            "resy_password": "pass456",
            "resy_cookies": "",
        })
    assert resp.status_code == 200
    assert db.get_config("resy_api_key") == "key123"
    assert db.get_config("resy_email") == "test@test.com"
```

- [ ] **Step 3: Implement main.py**

`backend/main.py`:
```python
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from database import Database
from aws import AWSClient
from routers import targets, settings as settings_router, reservations

load_dotenv()
logging.basicConfig(level=logging.INFO)


def create_app(db=None, aws_client=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _db = db or Database(region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
        app.state.db = _db

        lambda_arn = os.environ.get("LAMBDA_ARN", "")
        _aws = aws_client or AWSClient(
            region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            lambda_arn=lambda_arn,
        )
        app.state.aws_client = _aws

        _db.complete_past_targets()

        yield

    app = FastAPI(title="Resy Bot", lifespan=lifespan)

    cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if db is not None and aws_client is not None:
        app.state.db = db
        app.state.aws_client = aws_client

    app.include_router(targets.router)
    app.include_router(settings_router.router)
    app.include_router(reservations.router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
    if os.path.isdir(frontend_dist):
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")

    return app


app = create_app()
```

- [ ] **Step 4: Implement routers/targets.py**

`backend/routers/targets.py`:
```python
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from typing import Optional
from auth import require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/targets", tags=["targets"])


class TargetCreate(BaseModel):
    venue_id: str
    venue_name: str
    date: str
    party_size: int
    opening_time: str
    preferred_time: Optional[str] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None


def _opening_time_to_cron(opening_time: datetime) -> str:
    """Convert a UTC datetime to an EventBridge cron expression, 2 min before."""
    t = opening_time.astimezone(timezone.utc) - timedelta(minutes=2)
    return f"cron({t.minute} {t.hour} {t.day} {t.month} ? {t.year})"


@router.get("", dependencies=[Depends(require_api_key)])
async def list_targets(request: Request):
    return request.app.state.db.get_all_targets()


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_api_key)])
async def add_target(body: TargetCreate, request: Request):
    db = request.app.state.db
    aws = request.app.state.aws_client
    target_data = body.model_dump()
    target_id = db.insert_target(target_data)
    target = db.get_target(target_id)

    rule_name = f"resy-bot-target-{target_id}"
    opening_time = datetime.fromisoformat(body.opening_time)
    if opening_time.tzinfo is None:
        opening_time = opening_time.replace(tzinfo=timezone.utc)
    cron_expr = _opening_time_to_cron(opening_time)
    try:
        aws.create_start_rule(rule_name, cron_expr, target_id)
    except Exception as e:
        logger.warning(f"EventBridge rule creation failed: {e}")

    return target


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_api_key)])
async def delete_target(target_id: str, request: Request):
    db = request.app.state.db
    aws = request.app.state.aws_client
    deleted = db.delete_target_if_pending(target_id)
    if not deleted:
        raise HTTPException(status_code=409, detail="Target is not pending and cannot be deleted")
    try:
        aws.delete_rule(f"resy-bot-target-{target_id}")
    except Exception as e:
        logger.warning(f"EventBridge rule deletion failed: {e}")
```

- [ ] **Step 5: Implement routers/settings.py**

`backend/routers/settings.py`:
```python
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from auth import require_api_key
from config import Settings, load_settings, save_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsBody(BaseModel):
    resy_api_key: str = ""
    resy_email: str = ""
    resy_password: str = ""
    resy_cookies: str = ""


@router.get("", dependencies=[Depends(require_api_key)])
async def get_settings(request: Request):
    settings = load_settings(request.app.state.db)
    return settings.__dict__


@router.put("", dependencies=[Depends(require_api_key)])
async def update_settings(body: SettingsBody, request: Request):
    settings = Settings(**body.model_dump())
    save_settings(request.app.state.db, settings)
    return settings.__dict__
```

- [ ] **Step 6: Update routers/reservations.py**

`backend/routers/reservations.py`:
```python
import logging
from fastapi import APIRouter, Depends, Request
from auth import require_api_key
from config import load_settings
from resy import ResyClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reservations", tags=["reservations"])


@router.get("", dependencies=[Depends(require_api_key)])
async def get_reservations(request: Request):
    db = request.app.state.db
    settings = load_settings(db)
    if not settings.resy_api_key:
        return []
    client = ResyClient(
        api_key=settings.resy_api_key,
        email=settings.resy_email,
        password=settings.resy_password,
        cookies=settings.resy_cookies,
    )
    try:
        await client.connect()
        return await client.get_reservations()
    except Exception as e:
        logger.error(f"Failed to fetch reservations: {e}")
        return []
    finally:
        await client.close()
```

- [ ] **Step 7: Run tests**

```bash
cd backend
python -m pytest tests/test_targets.py tests/test_settings.py -v
```

Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/main.py backend/routers/targets.py backend/routers/settings.py backend/routers/reservations.py backend/tests/test_targets.py backend/tests/test_settings.py
git commit -m "feat: update dashboard backend — DynamoDB + Lambda architecture"
```

---

## Task 9: Frontend Updates

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/pages/TargetsPage.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/components/StatusBadge.tsx`

- [ ] **Step 1: Update api.ts**

Replace the full contents of `frontend/src/api.ts`:

```typescript
const API_KEY = import.meta.env.VITE_API_KEY ?? "";
const BASE = (import.meta.env.VITE_API_BASE ?? "") + "/api";

function headers(): HeadersInit {
  return { "Content-Type": "application/json", "x-api-key": API_KEY };
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method,
    headers: headers(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) throw new Error(`${method} ${path} → ${resp.status}`);
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

export interface Target {
  id: string;
  venue_id: string;
  venue_name: string;
  date: string;
  party_size: number;
  opening_time: string;
  preferred_time: string | null;
  window_start: string | null;
  window_end: string | null;
  status: "pending" | "sniping" | "booked" | "failed" | "completed";
  booked_at: string | null;
  reservation_details: string | null;
}

export interface TargetCreate {
  venue_id: string;
  venue_name: string;
  date: string;
  party_size: number;
  opening_time: string;
  preferred_time?: string;
  window_start?: string;
  window_end?: string;
}

export interface AppSettings {
  resy_api_key: string;
  resy_email: string;
  resy_password: string;
  resy_cookies: string;
}

export interface Reservation {
  venue: { name: string };
  date: string;
  time_slot: string;
  party_size: number;
  resy_token: string;
  [key: string]: unknown;
}

export const api = {
  targets: {
    list: () => request<Target[]>("GET", "/targets"),
    add: (t: TargetCreate) => request<Target>("POST", "/targets", t),
    delete: (id: string) => request<void>("DELETE", `/targets/${id}`),
  },
  settings: {
    get: () => request<AppSettings>("GET", "/settings"),
    update: (s: AppSettings) => request<AppSettings>("PUT", "/settings", s),
  },
  reservations: {
    list: () => request<Reservation[]>("GET", "/reservations"),
  },
};
```

- [ ] **Step 2: Update StatusBadge.tsx**

`frontend/src/components/StatusBadge.tsx`:
```tsx
const COLORS: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  sniping: "bg-blue-100 text-blue-800 animate-pulse",
  booked: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  completed: "bg-gray-100 text-gray-500",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${COLORS[status] ?? "bg-gray-100 text-gray-800"}`}>
      {status}
    </span>
  );
}
```

- [ ] **Step 3: Update TargetsPage.tsx**

Replace the full contents of `frontend/src/pages/TargetsPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api, Target, TargetCreate, Reservation } from "../api";
import { StatusBadge } from "../components/StatusBadge";

const EMPTY_FORM: TargetCreate = {
  venue_id: "", venue_name: "", date: "", party_size: 2,
  opening_time: "", preferred_time: "", window_start: "", window_end: "",
};

function StatCard({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div className={`rounded-lg border p-4 ${color ?? "bg-white"}`}>
      <p className="text-sm text-gray-500">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  );
}

export function TargetsPage() {
  const [targets, setTargets] = useState<Target[]>([]);
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [form, setForm] = useState<TargetCreate>(EMPTY_FORM);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [resLoading, setResLoading] = useState(false);

  async function loadTargets() {
    try { setTargets(await api.targets.list()); } catch { setError("Failed to load targets"); }
  }

  async function loadReservations() {
    setResLoading(true);
    try { setReservations(await api.reservations.list()); } catch { /* ignore */ }
    finally { setResLoading(false); }
  }

  useEffect(() => { loadTargets(); loadReservations(); }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setAdding(true);
    setError("");
    try {
      await api.targets.add(form);
      setForm(EMPTY_FORM);
      await loadTargets();
    } catch {
      setError("Failed to add target");
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(id: string) {
    try { await api.targets.delete(id); await loadTargets(); }
    catch { setError("Failed to delete target (may not be pending)"); }
  }

  const activeTargets = targets.filter(t => t.status !== "completed");
  const completedTargets = targets.filter(t => t.status === "completed");

  const field = (label: string, key: keyof TargetCreate, type = "text", extra?: object) => (
    <div className="flex flex-col gap-1">
      <label className="text-sm font-medium text-gray-700">{label}</label>
      <input
        type={type}
        className="border rounded px-3 py-1.5 text-sm"
        value={String(form[key] ?? "")}
        onChange={e => setForm(f => ({ ...f, [key]: type === "number" ? Number(e.target.value) : e.target.value }))}
        {...extra}
      />
    </div>
  );

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-8">
      <h1 className="text-2xl font-bold">Snipe Targets</h1>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <div className="grid grid-cols-4 gap-3">
        <StatCard label="Total" value={activeTargets.length} />
        <StatCard label="Pending" value={activeTargets.filter(t => t.status === "pending").length} />
        <StatCard label="Sniping" value={activeTargets.filter(t => t.status === "sniping").length} />
        <StatCard label="Booked" value={activeTargets.filter(t => t.status === "booked").length} />
      </div>

      <form onSubmit={handleAdd} className="bg-white border rounded-lg p-5 grid grid-cols-2 gap-4 shadow-sm">
        <h2 className="col-span-2 font-semibold text-gray-800">Add Target</h2>
        {field("Venue ID", "venue_id", "text", { required: true })}
        {field("Venue Name", "venue_name", "text", { required: true })}
        {field("Date", "date", "date", { required: true })}
        {field("Party Size", "party_size", "number", { min: 1, max: 20, required: true })}
        {field("Opening Time (UTC)", "opening_time", "datetime-local", { required: true })}
        {field("Preferred Time (optional)", "preferred_time", "time")}
        {field("Window Start (optional)", "window_start", "time")}
        {field("Window End (optional)", "window_end", "time")}
        <div className="col-span-2">
          <button type="submit" disabled={adding}
            className="bg-indigo-600 text-white px-5 py-2 rounded text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
            {adding ? "Adding..." : "Add Target"}
          </button>
        </div>
      </form>

      <div className="space-y-3">
        <h2 className="font-semibold text-gray-800">Active Targets</h2>
        {activeTargets.length === 0 && <p className="text-gray-500 text-sm">No active targets.</p>}
        {activeTargets.map(t => (
          <div key={t.id} className="bg-white border rounded-lg p-4 flex items-center justify-between shadow-sm">
            <div>
              <p className="font-medium">{t.venue_name}</p>
              <p className="text-sm text-gray-500">
                {t.date} · Party of {t.party_size} · Opens {t.opening_time}
              </p>
              {t.preferred_time && <p className="text-xs text-gray-400">Preferred: {t.preferred_time}</p>}
              {(t.window_start || t.window_end) && (
                <p className="text-xs text-gray-400">
                  Window: {t.window_start || "any"} – {t.window_end || "any"}
                </p>
              )}
              {t.booked_at && <p className="text-xs text-green-600 mt-1">Booked at {t.booked_at}</p>}
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge status={t.status} />
              {t.status === "pending" && (
                <button onClick={() => handleDelete(t.id)}
                  className="text-red-500 hover:text-red-700 text-sm">Delete</button>
              )}
            </div>
          </div>
        ))}
      </div>

      {completedTargets.length > 0 && (
        <div className="space-y-3">
          <h2 className="font-semibold text-gray-400">Completed</h2>
          {completedTargets.map(t => (
            <div key={t.id} className="bg-gray-50 border border-gray-200 rounded-lg p-4 flex items-center justify-between opacity-60">
              <div>
                <p className="font-medium text-gray-500">{t.venue_name}</p>
                <p className="text-sm text-gray-400">{t.date} · Party of {t.party_size}</p>
              </div>
              <StatusBadge status={t.status} />
            </div>
          ))}
        </div>
      )}

      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <h2 className="font-semibold text-gray-800">Upcoming Reservations</h2>
          <button onClick={loadReservations} disabled={resLoading}
            className="text-sm text-indigo-600 hover:text-indigo-800 disabled:opacity-50">
            {resLoading ? "Loading..." : "Refresh"}
          </button>
        </div>
        {reservations.length === 0 && <p className="text-gray-500 text-sm">No upcoming reservations.</p>}
        {reservations.map((r, i) => (
          <div key={i} className="bg-white border rounded-lg p-4 shadow-sm">
            <p className="font-medium">{r.venue?.name}</p>
            <p className="text-sm text-gray-500">{r.date} · {r.time_slot} · Party of {r.party_size}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Update SettingsPage.tsx**

Replace the full contents of `frontend/src/pages/SettingsPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api, AppSettings } from "../api";

const EMPTY: AppSettings = {
  resy_api_key: "", resy_email: "",
  resy_password: "", resy_cookies: "",
};

export function SettingsPage() {
  const [form, setForm] = useState<AppSettings>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.settings.get().then(setForm).catch(() => setError("Failed to load settings"));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true); setError(""); setSaved(false);
    try {
      await api.settings.update(form);
      setSaved(true);
    } catch {
      setError("Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  const field = (label: string, key: keyof AppSettings, type = "text") => (
    <div className="flex flex-col gap-1">
      <label className="text-sm font-medium text-gray-700">{label}</label>
      <input type={type} className="border rounded px-3 py-1.5 text-sm font-mono"
        value={form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
    </div>
  );

  return (
    <div className="max-w-xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>
      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}
      {saved && <p className="text-green-600 text-sm mb-4">Settings saved.</p>}
      <form onSubmit={handleSubmit} className="bg-white border rounded-lg p-5 space-y-4 shadow-sm">
        <h2 className="font-semibold text-gray-800">Resy Credentials</h2>
        <p className="text-xs text-gray-500">Find these in your browser's Network tab when browsing Resy.</p>
        {field("API Key", "resy_api_key")}
        {field("Email", "resy_email")}
        {field("Password", "resy_password", "password")}
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-gray-700">Browser Cookies (optional)</label>
          <textarea className="border rounded px-3 py-1.5 text-sm font-mono h-20"
            value={form.resy_cookies}
            onChange={e => setForm(f => ({ ...f, resy_cookies: e.target.value }))}
            placeholder="Paste cookie string from browser DevTools" />
        </div>
        <button type="submit" disabled={saving}
          className="bg-indigo-600 text-white px-5 py-2 rounded text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
          {saving ? "Saving..." : "Save Settings"}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 5: Verify frontend builds**

```bash
cd frontend
npm run build
```

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/StatusBadge.tsx frontend/src/pages/TargetsPage.tsx frontend/src/pages/SettingsPage.tsx
git commit -m "feat: update frontend — new time fields, completed status, remove Twilio"
```

---

## Task 10: Deployment & Cleanup

**Files:**
- Create: `deploy/deploy.sh`
- Rewrite: `deploy/IAM_SETUP.md`
- Delete: `deploy/setup.sh`, `deploy/resy-bot.service`, `deploy/nginx.conf`
- Delete: `backend/scheduler.py`, `backend/sms.py`
- Delete: `backend/tests/test_scheduler.py`, `backend/tests/test_sms.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Create deploy/deploy.sh**

`deploy/deploy.sh`:
```bash
#!/bin/bash
set -e

FUNCTION_NAME="resy-bot-snipe"
BUILD_DIR=$(mktemp -d)

echo "Installing dependencies..."
pip install httpx boto3 -t "$BUILD_DIR" --quiet

echo "Copying source files..."
cp backend/lambda_handler.py "$BUILD_DIR/"
cp backend/resy.py "$BUILD_DIR/"
cp backend/snipe.py "$BUILD_DIR/"
cp backend/database.py "$BUILD_DIR/"
cp backend/config.py "$BUILD_DIR/"

echo "Creating zip..."
cd "$BUILD_DIR"
zip -r9 /tmp/resy-bot-lambda.zip . --quiet

echo "Uploading to Lambda..."
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file fileb:///tmp/resy-bot-lambda.zip

echo "Cleaning up..."
rm -rf "$BUILD_DIR" /tmp/resy-bot-lambda.zip

echo "Deploy complete."
```

- [ ] **Step 2: Rewrite IAM_SETUP.md**

`deploy/IAM_SETUP.md`:
```markdown
# IAM Setup for Resy Bot (Lambda Architecture)

---

## Step 1: Create DynamoDB Tables

In AWS Console → DynamoDB → Create table:

1. **resy-bot-targets**
   - Partition key: `id` (String)
   - Capacity: On-demand
   
2. **resy-bot-config**
   - Partition key: `key` (String)
   - Capacity: On-demand

---

## Step 2: Create Lambda IAM Role

1. IAM → Roles → Create Role
2. Trusted entity: **Lambda** (`lambda.amazonaws.com`)
3. Name: `ResyBotLambdaRole`
4. Add inline policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Scan"],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:*:table/resy-bot-targets",
        "arn:aws:dynamodb:us-east-1:*:table/resy-bot-config"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

---

## Step 3: Create Lambda Function

1. Lambda → Create function
2. Name: `resy-bot-snipe`
3. Runtime: Python 3.12
4. Architecture: x86_64
5. Execution role: `ResyBotLambdaRole`
6. Memory: 256 MB
7. Timeout: 5 minutes

After creation, deploy code:
```bash
./deploy/deploy.sh
```

---

## Step 4: Add EventBridge Permission to Lambda

Allow EventBridge to invoke the Lambda function:

```bash
aws lambda add-permission \
  --function-name resy-bot-snipe \
  --statement-id eventbridge-invoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com
```

---

## Step 5: Create Local IAM User

1. IAM → Users → Create user
2. Name: `ResyBotLocal`
3. Attach inline policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
        "dynamodb:DeleteItem", "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:*:table/resy-bot-targets",
        "arn:aws:dynamodb:us-east-1:*:table/resy-bot-config"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "events:PutRule", "events:PutTargets",
        "events:DeleteRule", "events:RemoveTargets"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["lambda:GetFunction"],
      "Resource": "arn:aws:lambda:us-east-1:*:function:resy-bot-snipe"
    }
  ]
}
```

4. Create access key for this user
5. Run `aws configure` on your laptop with the access key

---

## Step 6: Configure Local Environment

Create `backend/.env`:
```
DASHBOARD_API_KEY=<pick-a-strong-key>
LAMBDA_ARN=arn:aws:lambda:us-east-1:<account-id>:function:resy-bot-snipe
AWS_DEFAULT_REGION=us-east-1
CORS_ORIGINS=http://localhost:5173
```

Create `frontend/.env.local`:
```
VITE_API_KEY=<same-key-as-above>
VITE_API_BASE=http://localhost:8000
```

---

## Summary of Resources

| Resource | Purpose |
|---|---|
| DynamoDB `resy-bot-targets` | Stores snipe targets |
| DynamoDB `resy-bot-config` | Stores Resy credentials |
| Lambda `resy-bot-snipe` | Executes snipes |
| IAM role `ResyBotLambdaRole` | Lambda execution permissions |
| IAM user `ResyBotLocal` | Local dashboard AWS access |
| EventBridge rules | One per target, triggers Lambda |
```

- [ ] **Step 3: Update .env.example**

`backend/.env.example`:
```
DASHBOARD_API_KEY=change-me
LAMBDA_ARN=arn:aws:lambda:us-east-1:ACCOUNT_ID:function:resy-bot-snipe
AWS_DEFAULT_REGION=us-east-1
CORS_ORIGINS=http://localhost:5173
```

- [ ] **Step 4: Delete old files**

```bash
rm backend/scheduler.py backend/sms.py
rm backend/tests/test_scheduler.py backend/tests/test_sms.py
rm deploy/setup.sh deploy/resy-bot.service deploy/nginx.conf
```

- [ ] **Step 5: Run full test suite**

```bash
cd backend
python -m pytest tests/ -v
```

Expected: All tests pass. No imports of deleted modules.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: Lambda deployment script, IAM docs, remove EC2 deployment files"
```

---

## Task 11: Final Verification

- [ ] **Step 1: Run full backend test suite**

```bash
cd backend
python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Build frontend**

```bash
cd frontend
npm run build
```

Expected: No TypeScript errors, build succeeds.

- [ ] **Step 3: Start local dashboard**

```bash
cd backend
uvicorn main:app --reload --port 8000 &
cd ../frontend
npm run dev &
```

Open `http://localhost:5173` — verify:
- Targets page loads (may show "Failed to load" if AWS not configured — that's expected)
- Settings page loads with Resy credential fields only (no Twilio)
- Add target form shows preferred_time, window_start, window_end fields

Stop both servers.

- [ ] **Step 4: Commit any fixes**

If any issues found, fix and commit.
