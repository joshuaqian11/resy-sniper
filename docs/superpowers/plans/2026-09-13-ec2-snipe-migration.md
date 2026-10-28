# EC2 Snipe Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Lambda-based snipe execution with EC2 + Playwright so Resy's Imperva WAF doesn't block requests, while keeping EventBridge as the scheduler and DynamoDB as the data store.

**Architecture:** EventBridge fires 2 min before opening time → triggers a lightweight Lambda that starts an EC2 instance and passes the target ID via SSM parameter → EC2 boots, runs a startup script that reads the target ID, executes the snipe with Playwright, then stops itself. The FastAPI dashboard continues to run locally (or wherever) and manages targets/EventBridge rules.

**Tech Stack:** Python 3.12, Playwright (Chromium), boto3, DynamoDB, EventBridge, Lambda (trigger only), EC2 (t3.micro), SSM Parameter Store

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `backend/resy.py` | **Rewrite** | Restore Playwright-based Resy client (from pre-Lambda version at commit `07f55bd`) |
| `backend/snipe_runner.py` | **Create** | EC2 entry point: reads target ID from SSM, runs snipe, stops instance |
| `backend/snipe.py` | **Modify** | Remove `import httpx` inside `_book_with_retry`, use Playwright exception handling |
| `backend/aws.py` | **Rewrite** | Add EC2 start/stop/SSM methods, update EventBridge to start EC2 instead of invoke Lambda |
| `backend/routers/targets.py` | **Modify** | Update to use new `aws.py` interface (EC2 instance ID instead of Lambda ARN) |
| `backend/main.py` | **Modify** | Pass EC2 instance ID to AWSClient instead of Lambda ARN |
| `backend/lambda_handler.py` | **Rewrite** | Thin trigger: start EC2 instance, write target ID to SSM, return |
| `backend/requirements.txt` | **Modify** | Add `playwright` back, remove `httpcore[asyncio]` |
| `deploy/deploy.sh` | **Rewrite** | Lambda deploy for the thin trigger (no Playwright needed in Lambda) |
| `deploy/ec2-setup.sh` | **Create** | EC2 bootstrap: install Python, Playwright, Chromium, app code |
| `deploy/ec2-userdata.sh` | **Create** | EC2 User Data script: runs on every start, executes snipe_runner.py |

---

### Task 1: Restore Playwright-based Resy Client

**Files:**
- Rewrite: `backend/resy.py`
- Modify: `backend/requirements.txt`

The current `resy.py` uses `httpx`, which gets blocked by Imperva WAF. Restore the Playwright-based version from commit `07f55bd`, adapted to the current interface (the current code uses `auth_token` param and has a `close()` method the rest of the codebase expects).

- [ ] **Step 1: Update requirements.txt**

Replace the httpx/httpcore deps with Playwright:

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
playwright==1.49.1
boto3==1.35.40
python-dotenv==1.0.1
```

- [ ] **Step 2: Rewrite resy.py with Playwright**

Replace the contents of `backend/resy.py` with:

```python
import json
import logging
from urllib.parse import urlencode
from playwright.async_api import async_playwright
from typing import Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://api.resy.com"


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

    def _headers(self) -> dict:
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
        return headers

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

        if not self.auth_token and self.email and self.password:
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
        qs = urlencode(params)
        url = f"{BASE_URL}{path}?{qs}"
        resp = await self._request.get(url, headers=self._headers())
        if not resp.ok:
            body = await resp.text()
            raise Exception(f"HTTP {resp.status} from {path}: {body[:200]}")
        return await resp.json()

    async def _post_form(self, path: str, payload: dict, headers: dict = None) -> dict:
        hdrs = headers or self._headers()
        hdrs["content-type"] = "application/x-www-form-urlencoded"
        resp = await self._request.post(
            f"{BASE_URL}{path}",
            data=urlencode(payload),
            headers=hdrs,
        )
        if resp.status == 401 and self.email and self.password:
            logger.info("Got 401 — refreshing auth token")
            await self._login()
            hdrs = headers or self._headers()
            hdrs["content-type"] = "application/x-www-form-urlencoded"
            resp = await self._request.post(
                f"{BASE_URL}{path}",
                data=urlencode(payload),
                headers=hdrs,
            )
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
        book_headers = self._headers()
        book_headers["origin"] = "https://widgets.resy.com"
        book_headers["referer"] = "https://widgets.resy.com/"
        book_headers["x-origin"] = "https://widgets.resy.com"
        return await self._post_form("/3/book", {
            "book_token": book_token,
            "struct_payment_method": json.dumps({"id": self.payment_method_id}),
            "source_id": "resy.com-venue-details",
        }, headers=book_headers)

    async def get_reservations(self) -> list[dict]:
        resp = await self._request.get(
            f"{BASE_URL}/3/user/reservations",
            headers=self._headers(),
        )
        if not resp.ok:
            raise Exception(f"HTTP {resp.status} from /3/user/reservations")
        return (await resp.json()).get("reservations", [])
```

- [ ] **Step 3: Install Playwright and Chromium locally**

Run:
```bash
cd backend && pip install playwright==1.49.1 && playwright install chromium
```

- [ ] **Step 4: Commit**

```bash
git add backend/resy.py backend/requirements.txt
git commit -m "feat: restore Playwright-based Resy client for Imperva WAF bypass"
```

---

### Task 2: Update snipe.py for Playwright

**Files:**
- Modify: `backend/snipe.py`

The current `snipe.py` imports `httpx` inside `_book_with_retry` to check for `httpx.TimeoutException`. With Playwright, timeouts raise `playwright.async_api.TimeoutError` or generic `Exception`. Update accordingly.

- [ ] **Step 1: Update _book_with_retry in snipe.py**

Replace the `_book_with_retry` function:

```python
async def _book_with_retry(resy_client, book_token: str) -> dict:
    while True:
        try:
            return await resy_client.book(book_token)
        except Exception as e:
            if "timeout" in str(e).lower():
                logger.warning("Book request timed out — retrying with same token")
                continue
            raise
```

- [ ] **Step 2: Commit**

```bash
git add backend/snipe.py
git commit -m "fix: update snipe timeout handling for Playwright"
```

---

### Task 3: Rewrite aws.py — EC2 + SSM + EventBridge

**Files:**
- Rewrite: `backend/aws.py`

The current `aws.py` targets Lambda. Rewrite it to:
- Start/stop EC2 instances
- Write target ID to SSM Parameter Store (so EC2 knows which target to snipe)
- Create EventBridge rules that invoke a Lambda (which starts EC2), not Lambda directly

- [ ] **Step 1: Rewrite aws.py**

```python
import json
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

SSM_PARAM_NAME = "/resy-bot/pending-target-id"


class AWSClient:
    def __init__(self, region: str, instance_id: str, lambda_arn: str):
        self.region = region
        self.instance_id = instance_id
        self.lambda_arn = lambda_arn
        self._events = boto3.client("events", region_name=region)
        self._ec2 = boto3.client("ec2", region_name=region)
        self._ssm = boto3.client("ssm", region_name=region)

    def set_target_param(self, target_id: str):
        """Write the target ID to SSM so the EC2 instance knows what to snipe."""
        self._ssm.put_parameter(
            Name=SSM_PARAM_NAME,
            Value=target_id,
            Type="String",
            Overwrite=True,
        )
        logger.info(f"Set SSM param {SSM_PARAM_NAME} = {target_id}")

    def get_target_param(self) -> str:
        """Read the target ID from SSM."""
        resp = self._ssm.get_parameter(Name=SSM_PARAM_NAME)
        return resp["Parameter"]["Value"]

    def start_instance(self):
        """Start the snipe EC2 instance."""
        self._ec2.start_instances(InstanceIds=[self.instance_id])
        logger.info(f"Starting EC2 instance {self.instance_id}")

    def stop_instance(self):
        """Stop the snipe EC2 instance."""
        try:
            self._ec2.stop_instances(InstanceIds=[self.instance_id])
            logger.info(f"Stopping EC2 instance {self.instance_id}")
        except Exception as e:
            logger.error(f"Failed to stop instance: {e}")

    def create_start_rule(self, rule_name: str, cron_expression: str, target_id: str):
        """Create an EventBridge rule that invokes the trigger Lambda on a schedule."""
        self._events.put_rule(
            Name=rule_name,
            ScheduleExpression=cron_expression,
            State="ENABLED",
            Description=f"Resy bot snipe trigger for target {target_id}",
        )
        self._events.put_targets(
            Rule=rule_name,
            Targets=[{
                "Id": "invoke-trigger-lambda",
                "Arn": self.lambda_arn,
                "Input": json.dumps({"target_id": target_id}),
            }],
        )

    def delete_rule(self, rule_name: str):
        """Remove targets then delete the EventBridge rule."""
        try:
            self._events.remove_targets(Rule=rule_name, Ids=["invoke-trigger-lambda"])
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

- [ ] **Step 2: Commit**

```bash
git add backend/aws.py
git commit -m "feat: rewrite AWS client — EC2 start/stop, SSM params, EventBridge→Lambda trigger"
```

---

### Task 4: Rewrite Lambda Handler — Thin EC2 Trigger

**Files:**
- Rewrite: `backend/lambda_handler.py`

The Lambda no longer runs the snipe itself. It just:
1. Writes the target ID to SSM
2. Starts the EC2 instance

- [ ] **Step 1: Rewrite lambda_handler.py**

```python
import logging
import boto3

logger = logging.getLogger(__name__)

SSM_PARAM_NAME = "/resy-bot/pending-target-id"


def handler(event, context):
    target_id = event.get("target_id")
    if not target_id:
        logger.error("No target_id in event")
        return {"statusCode": 400, "body": "Missing target_id"}

    region = "us-east-1"
    instance_id = event.get("instance_id", "")

    # Read instance_id from environment if not in event
    import os
    instance_id = instance_id or os.environ.get("EC2_INSTANCE_ID", "")
    if not instance_id:
        logger.error("No EC2 instance ID configured")
        return {"statusCode": 500, "body": "Missing EC2_INSTANCE_ID"}

    ssm = boto3.client("ssm", region_name=region)
    ec2 = boto3.client("ec2", region_name=region)

    # Write target ID to SSM so EC2 knows what to snipe
    ssm.put_parameter(
        Name=SSM_PARAM_NAME,
        Value=target_id,
        Type="String",
        Overwrite=True,
    )
    logger.info(f"Set SSM param {SSM_PARAM_NAME} = {target_id}")

    # Start the EC2 instance
    ec2.start_instances(InstanceIds=[instance_id])
    logger.info(f"Started EC2 instance {instance_id} for target {target_id}")

    return {"statusCode": 200, "body": f"Started EC2 for target {target_id}"}
```

- [ ] **Step 2: Commit**

```bash
git add backend/lambda_handler.py
git commit -m "feat: rewrite Lambda handler as thin EC2 trigger"
```

---

### Task 5: Create EC2 Snipe Runner

**Files:**
- Create: `backend/snipe_runner.py`

This is the script that runs on EC2 when it boots. It:
1. Reads the target ID from SSM
2. Loads config from DynamoDB
3. Runs the snipe with Playwright
4. Stops the EC2 instance when done

- [ ] **Step 1: Create snipe_runner.py**

```python
#!/usr/bin/env python3
"""EC2 entry point: read target from SSM, run snipe with Playwright, stop instance."""
import asyncio
import logging
import boto3
import urllib.request
from datetime import datetime, timezone
from database import Database
from resy import ResyClient
from snipe import run_snipe

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

SSM_PARAM_NAME = "/resy-bot/pending-target-id"
REGION = "us-east-1"


def get_instance_id() -> str:
    """Fetch this instance's ID from EC2 metadata (IMDSv2)."""
    try:
        token_req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
        )
        with urllib.request.urlopen(token_req, timeout=2) as r:
            token = r.read().decode()
        req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.read().decode()
    except Exception:
        return ""


async def main():
    ssm = boto3.client("ssm", region_name=REGION)
    ec2 = boto3.client("ec2", region_name=REGION)

    # Read target ID from SSM
    try:
        resp = ssm.get_parameter(Name=SSM_PARAM_NAME)
        target_id = resp["Parameter"]["Value"]
    except Exception as e:
        logger.error(f"Failed to read target ID from SSM: {e}")
        return

    logger.info(f"Snipe runner started for target {target_id}")

    db = Database(region=REGION)
    target = db.get_target(target_id)

    if not target:
        logger.error(f"Target {target_id} not found in DynamoDB")
        return

    if target["status"] != "pending":
        logger.info(f"Target {target_id} status is {target['status']}, skipping")
        return

    config = db.get_all_config()
    resy_client = ResyClient(
        api_key=config.get("resy_api_key", ""),
        auth_token=config.get("resy_auth_token", ""),
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

        # Wait until opening time
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

    updated = db.get_target(target_id)
    status = updated["status"] if updated else "unknown"
    logger.info(f"Snipe complete — status: {status}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # Stop this EC2 instance
        instance_id = get_instance_id()
        if instance_id:
            logger.info(f"Stopping instance {instance_id}")
            ec2 = boto3.client("ec2", region_name=REGION)
            ec2.stop_instances(InstanceIds=[instance_id])
        else:
            logger.warning("Could not determine instance ID — instance will not auto-stop")
```

- [ ] **Step 2: Commit**

```bash
git add backend/snipe_runner.py
git commit -m "feat: EC2 snipe runner — reads SSM, runs Playwright snipe, auto-stops"
```

---

### Task 6: Update Dashboard Backend (main.py + targets router)

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/routers/targets.py`

Update to pass `instance_id` to AWSClient alongside `lambda_arn`.

- [ ] **Step 1: Update main.py**

In `main.py`, change the AWSClient initialization inside `lifespan`:

```python
lambda_arn = os.environ.get("LAMBDA_ARN", "")
ec2_instance_id = os.environ.get("EC2_INSTANCE_ID", "")
_aws = aws_client or AWSClient(
    region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    instance_id=ec2_instance_id,
    lambda_arn=lambda_arn,
)
```

- [ ] **Step 2: Commit**

```bash
git add backend/main.py
git commit -m "feat: pass EC2 instance ID to AWSClient in dashboard startup"
```

---

### Task 7: EC2 Deployment Scripts

**Files:**
- Create: `deploy/ec2-setup.sh`
- Create: `deploy/ec2-userdata.sh`
- Rewrite: `deploy/deploy.sh`

- [ ] **Step 1: Create ec2-setup.sh (one-time instance setup)**

```bash
#!/bin/bash
# Run once on a fresh EC2 instance (Amazon Linux 2023) to install dependencies.
set -e

echo "Installing system packages..."
sudo dnf update -y
sudo dnf install -y python3.12 python3.12-pip git

echo "Installing Python dependencies..."
pip3.12 install playwright boto3

echo "Installing Chromium for Playwright..."
playwright install --with-deps chromium

echo "Creating app directory..."
sudo mkdir -p /opt/resy-bot
sudo chown ec2-user:ec2-user /opt/resy-bot

echo "EC2 setup complete."
```

- [ ] **Step 2: Create ec2-userdata.sh (runs on every boot)**

This is set as the EC2 User Data script. It runs each time the instance starts.

```bash
#!/bin/bash
# EC2 User Data — runs on every instance start.
# Pulls latest code from S3 and runs the snipe.
set -e

exec > /var/log/resy-bot.log 2>&1
echo "$(date) — Resy bot starting"

APP_DIR="/opt/resy-bot"
cd "$APP_DIR"

# Run the snipe
python3.12 snipe_runner.py

echo "$(date) — Snipe runner finished, instance will stop"
# Instance stops itself from within snipe_runner.py
```

- [ ] **Step 3: Rewrite deploy.sh for Lambda trigger + EC2 code sync**

```bash
#!/bin/bash
set -e

FUNCTION_NAME="resy-bot-snipe"
EC2_INSTANCE_ID="${EC2_INSTANCE_ID:?Set EC2_INSTANCE_ID env var}"
APP_DIR="/opt/resy-bot"

echo "=== Deploying Lambda trigger ==="
BUILD_DIR=$(mktemp -d)

pip3 install boto3 -t "$BUILD_DIR" --quiet \
  --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12

cp backend/lambda_handler.py "$BUILD_DIR/"

cd "$BUILD_DIR"
zip -r9 /tmp/resy-bot-lambda.zip . --quiet
cd -

aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file fileb:///tmp/resy-bot-lambda.zip

aws lambda update-function-configuration \
  --function-name "$FUNCTION_NAME" \
  --timeout 30 \
  --environment "Variables={EC2_INSTANCE_ID=$EC2_INSTANCE_ID}"

rm -rf "$BUILD_DIR" /tmp/resy-bot-lambda.zip
echo "Lambda trigger deployed."

echo ""
echo "=== Syncing code to EC2 ==="
# Copy app files to EC2 via SSM (no SSH needed)
for file in resy.py snipe.py snipe_runner.py database.py config.py; do
  echo "Uploading $file..."
  aws ssm send-command \
    --instance-id "$EC2_INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --parameters "commands=[\"cat > $APP_DIR/$file << 'FILEEOF'\n$(cat backend/$file)\nFILEEOF\"]" \
    --output text --query "Command.CommandId" > /dev/null
done

echo "Deploy complete."
```

- [ ] **Step 4: Commit**

```bash
git add deploy/
git commit -m "feat: EC2 deployment scripts — setup, userdata, deploy"
```

---

### Task 8: Update Lambda Timeout and Clean Up

**Files:**
- Modify: `deploy/deploy.sh` (already done in Task 7)

The Lambda is now just a trigger — it doesn't run for minutes. Reduce timeout from 5 min to 30 seconds (already handled in the deploy script above).

- [ ] **Step 1: Verify Lambda env var is set after deploy**

Run:
```bash
aws lambda get-function-configuration --function-name resy-bot-snipe \
  --query 'Environment.Variables'
```

Expected: `{"EC2_INSTANCE_ID": "<your-instance-id>"}`

- [ ] **Step 2: Delete old files that are no longer needed**

The `backend/test_resy.py` file (at project root, not in tests/) appears to be a duplicate/old file:

```bash
rm backend/test_resy.py
git add -u
git commit -m "chore: remove stale test file"
```

---

### Task 9: AWS Infrastructure Setup

This task is done in the AWS console (or CLI). No code changes.

- [ ] **Step 1: Create EC2 instance (if not already existing)**

```bash
# Create a t3.micro instance with Amazon Linux 2023
aws ec2 run-instances \
  --image-id ami-0c02fb55956c7d316 \
  --instance-type t3.micro \
  --key-name <your-key-pair> \
  --iam-instance-profile Name=resy-bot-ec2-role \
  --user-data file://deploy/ec2-userdata.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=resy-bot-snipe}]' \
  --query 'Instances[0].InstanceId' --output text
```

Note the instance ID — you'll need it for `EC2_INSTANCE_ID`.

- [ ] **Step 2: Create IAM role for EC2 (resy-bot-ec2-role)**

The EC2 instance needs permissions for:
- `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:UpdateItem`, `dynamodb:Scan` on `resy-bot-targets` and `resy-bot-config` tables
- `ssm:GetParameter` on `/resy-bot/pending-target-id`
- `ec2:StopInstances` on its own instance (for self-stop)

- [ ] **Step 3: Update Lambda IAM role**

The Lambda trigger needs:
- `ec2:StartInstances` on the snipe EC2 instance
- `ssm:PutParameter` on `/resy-bot/pending-target-id`

- [ ] **Step 4: Update Lambda environment variable**

```bash
aws lambda update-function-configuration \
  --function-name resy-bot-snipe \
  --environment "Variables={EC2_INSTANCE_ID=<your-instance-id>}"
```

- [ ] **Step 5: Run ec2-setup.sh on the instance**

```bash
# SSH in or use SSM Session Manager
aws ssm start-session --target <instance-id>
# Then run:
curl -s https://raw.githubusercontent.com/<your-repo>/main/deploy/ec2-setup.sh | bash
```

Or copy and run manually.

- [ ] **Step 6: Stop the instance (it should only run during snipes)**

```bash
aws ec2 stop-instances --instance-ids <instance-id>
```

---

### Task 10: End-to-End Test

- [ ] **Step 1: Deploy Lambda trigger**

```bash
EC2_INSTANCE_ID=<your-id> bash deploy/deploy.sh
```

- [ ] **Step 2: Sync code to EC2**

Either via the deploy script's SSM sync or by SSH/SCP:
```bash
scp backend/{resy.py,snipe.py,snipe_runner.py,database.py,config.py} ec2-user@<ec2-ip>:/opt/resy-bot/
```

- [ ] **Step 3: Test the Lambda trigger manually**

```bash
aws lambda invoke \
  --function-name resy-bot-snipe \
  --payload '{"target_id": "test-123"}' \
  /tmp/lambda-out.json && cat /tmp/lambda-out.json
```

Verify: EC2 instance starts, SSM parameter is set.

- [ ] **Step 4: Test EC2 snipe runner manually**

SSH into the instance and run:
```bash
cd /opt/resy-bot && python3.12 snipe_runner.py
```

Verify: reads target from DynamoDB, attempts Playwright connection, stops instance after completion.

- [ ] **Step 5: Test full flow via dashboard**

Add a target through the frontend, verify:
1. Target appears in DynamoDB
2. EventBridge rule is created
3. When the rule fires → Lambda starts EC2 → EC2 runs snipe → EC2 stops itself
