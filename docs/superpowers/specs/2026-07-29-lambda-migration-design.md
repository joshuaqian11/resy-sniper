# Resy Bot Lambda Migration — Design Spec

**Date:** 2026-07-29
**Status:** Approved

---

## Overview

Migrate the Resy snipe bot from an EC2-based architecture (instance stopped between snipes, EBS storage persists) to a fully serverless architecture using Lambda + DynamoDB + EventBridge. The dashboard runs locally on the developer's laptop. The goal is zero idle cost — no EC2 instance, no EBS volume, no running infrastructure between snipes.

---

## Architecture

```
Local (laptop)                              AWS
┌──────────────────────────┐    ┌───────────────────────────────────┐
│ FastAPI backend            │    │                                   │
│   - CRUD targets           │───▶│  DynamoDB                         │
│   - Save/load Resy creds   │    │    resy-bot-targets table         │
│                            │    │    resy-bot-config table           │
│ React frontend             │    │                                   │
│   - Dashboard UI           │    │  EventBridge                      │
│                            │    │    One scheduled rule per target   │
│ Vite dev server (port 5173)│    │    Fires 2 min before opening     │
└──────────────────────────┘    │         │                          │
                                 │         ▼                          │
                                 │  Lambda: resy-bot-snipe            │
                                 │    - Reads target + creds from DB  │
                                 │    - Pre-warms Resy connection     │
                                 │    - Sleeps until exact opening    │
                                 │    - Polls Resy, books slot        │
                                 │    - Writes result to DynamoDB     │
                                 └───────────────────────────────────┘
```

No EC2, no VPC, no security groups, no EBS, no nginx, no systemd, no certbot.

Local AWS auth via `aws configure` using an IAM user's access keys.

---

## Data Model

### `resy-bot-targets` table

| Attribute | Type | Key | Notes |
|---|---|---|---|
| `id` | String (UUID) | Partition key | Generated on create |
| `venue_id` | String | | From Resy |
| `venue_name` | String | | Display name |
| `date` | String | | Reservation date (YYYY-MM-DD) |
| `party_size` | Number | | |
| `opening_time` | String | | ISO 8601 UTC datetime |
| `preferred_time` | String | | Optional, HH:MM — bot picks slot closest to this |
| `window_start` | String | | Optional, HH:MM — hard floor, ignore slots before this |
| `window_end` | String | | Optional, HH:MM — hard ceiling, ignore slots after this |
| `status` | String | | `pending`, `sniping`, `booked`, `failed`, `completed` |
| `booked_at` | String | | ISO 8601, set on success |
| `reservation_details` | String | | JSON blob from Resy on success |
| `eventbridge_rule` | String | | Rule name, for cleanup on delete |

On-demand capacity. No GSIs needed (table will be scanned — fine at this scale).

### `resy-bot-config` table

| Attribute | Type | Key | Notes |
|---|---|---|---|
| `key` | String | Partition key | e.g., `resy_api_key` |
| `value` | String | | The config value |

Keys stored: `resy_api_key`, `resy_email`, `resy_password`, `resy_cookies`.

On-demand capacity.

---

## Target Status Lifecycle

```
pending → sniping → booked → completed
                   → failed → completed
```

- **pending**: target created, waiting for opening time
- **sniping**: Lambda is actively polling Resy (set at start of snipe)
- **booked**: reservation secured
- **failed**: snipe window expired or booking error
- **completed**: reservation date has passed (transition from booked or failed)

The `completed` transition happens on dashboard startup: the backend scans all `booked` and `failed` targets whose `date` is before today and sets their status to `completed`.

---

## Preferred Time vs Time Window

Two independent concepts applied when filtering available slots:

- **Time window** (`window_start`, `window_end`): hard boundaries. Slots outside this range are discarded entirely. Either or both can be omitted for no constraint.
- **Preferred time** (`preferred_time`): soft preference. Among slots that pass the window filter, the bot picks the one closest to this time. If omitted, the bot picks the first available slot.

Examples:
- `preferred_time=19:30`, no window → prefer 7:30pm but take anything available
- `window_start=18:00`, `window_end=21:00`, no preferred → take any slot between 6-9pm
- `preferred_time=19:30`, `window_start=18:00`, `window_end=21:00` → prefer 7:30pm, but only consider 6-9pm

---

## Lambda Function

**Name:** `resy-bot-snipe`
**Runtime:** Python 3.12
**Memory:** 256 MB
**Timeout:** 5 minutes (2 min pre-warm wait + 2 min polling + 1 min buffer)

**Trigger:** EventBridge scheduled rule, fires 2 minutes before the target's `opening_time`.

**Event payload:**
```json
{"target_id": "uuid-here"}
```

**Execution flow:**
1. Read target from DynamoDB by `target_id`
2. Read Resy credentials from config table
3. Create `ResyClient`, connect (pre-warm HTTP keep-alive)
4. Sleep until exact `opening_time`
5. Run snipe polling loop (existing `snipe.py` logic)
6. Write result to DynamoDB (`booked` + reservation details, or `failed`)
7. Return

**Packaged code (reused from current codebase):**
- `resy.py` — Resy API client (unchanged)
- `snipe.py` — polling loop, booking, retry logic (updated for preferred_time / window changes)

**New code:**
- `lambda_handler.py` — entry point, reads DynamoDB, calls `run_snipe`, writes result

**Deployment:** Zip package containing source files + pip-installed dependencies. Uploaded via `aws lambda update-function-code`.

---

## Dashboard (Local)

### Backend (FastAPI)

**Database layer** (`database.py`): Rewrite from aiosqlite to boto3 DynamoDB. Same method signatures:
- `insert_target()` — generates UUID, PutItem
- `get_all_targets()` — Scan
- `get_target(id)` — GetItem
- `update_target_status(id, status)` — UpdateItem
- `update_target_booked(id, details)` — UpdateItem (status + booked_at + reservation_details)
- `delete_target_if_pending(id)` — DeleteItem with ConditionExpression `status = pending`
- `get_config(key)` / `set_config(key, value)` / `get_all_config()` — GetItem / PutItem / Scan on config table
- `complete_past_targets()` — Scan for booked/failed with date < today, batch UpdateItem to `completed`

**Startup** (`main.py` lifespan):
- Init DynamoDB-backed database
- Call `complete_past_targets()`
- No scheduler, no EC2 instance ID lookup

**Targets router** (`routers/targets.py`):
- POST: store target in DynamoDB, create EventBridge rule (2 min before opening, targeting Lambda ARN)
- DELETE: delete EventBridge rule, delete target from DynamoDB
- GET: read from DynamoDB

**AWS client** (`aws.py`):
- Keep: `create_start_rule()`, `delete_rule()`
- Update: EventBridge target is now Lambda ARN instead of SSM automation
- Remove: `stop_self()`, `get_instance_id()`

**Config** (`config.py`):
- Fields: `resy_api_key`, `resy_email`, `resy_password`, `resy_cookies`
- No Twilio fields

**Removed files:**
- `scheduler.py` (EventBridge replaces APScheduler)
- `sms.py` (no Twilio for now)
- `deploy/setup.sh`, `deploy/resy-bot.service`, `deploy/nginx.conf`, `deploy/IAM_SETUP.md` (no EC2)

### Frontend (React)

- Update add-target form: replace `preferred_start`/`preferred_end` with `preferred_time`, `window_start`, `window_end`
- Show `completed` targets visually distinct (grayed out or separate section)
- No other changes to the React app

---

## AWS Resources

### Created manually (one-time)

| Resource | Config |
|---|---|
| DynamoDB table `resy-bot-targets` | Partition key: `id` (String), on-demand |
| DynamoDB table `resy-bot-config` | Partition key: `key` (String), on-demand |
| Lambda function `resy-bot-snipe` | Python 3.12, 256 MB, 5 min timeout |
| IAM role `ResyBotLambdaRole` | For the Lambda function |
| IAM user `ResyBotLocal` | For local dashboard to access AWS |

### IAM Role: `ResyBotLambdaRole`

Trust policy: `lambda.amazonaws.com`

Permissions:
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

### IAM User: `ResyBotLocal`

Permissions:
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

---

## Deployment

**Lambda deploy script** (`deploy/deploy.sh`):
1. `pip install` dependencies into a temp directory
2. Copy source files (`resy.py`, `snipe.py`, `lambda_handler.py`, etc.)
3. Zip everything
4. `aws lambda update-function-code --function-name resy-bot-snipe --zip-file fileb://...`

Run this when snipe logic changes. Dashboard changes don't need redeployment.

**Local dashboard:**
```bash
# Backend
cd backend && uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm run dev
```

---

## Cost

| Resource | Monthly cost |
|---|---|
| DynamoDB | ~$0.00 (free tier: 25 GB storage, 25 WCU/RCU) |
| Lambda | ~$0.00 (free tier: 1M requests, 400K GB-seconds) |
| EventBridge | ~$0.00 ($1 per million events) |
| **Total** | **$0.00** |

---

## Out of Scope

- Twilio / SMS notifications (will be added later)
- S3 backups
- CloudFormation / Terraform (manual resource creation for now)
- Multi-user support
- Docker / containerization
- CI/CD pipeline
