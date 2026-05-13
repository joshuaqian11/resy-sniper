# Resy Snipe Bot — Design Spec

**Date:** 2026-05-13  
**Status:** Approved

---

## Overview

A web-based bot that automatically snipes Resy reservations the moment they become available. The primary use case is restaurants that release reservations at a fixed time (e.g., 9 AM, 30 days in advance). The bot wakes up at the precise opening time, aggressively polls for availability, and books instantly — then sends an SMS confirmation.

---

## Architecture

Two components deployed together on a single EC2 t3.nano instance in `us-east-1`:

**Backend — Python + FastAPI (async)**
- Serves the dashboard REST API
- Runs the APScheduler instance for all snipe jobs
- Makes direct async HTTP calls to Resy's API via `httpx`
- Sends SMS via Twilio

**Frontend — React**
- Built once, served as static files via Nginx
- Communicates with the backend over a local API

**Scheduler — APScheduler**
- Runs inside the FastAPI process
- One independent job per snipe target, scheduled to fire at the target's opening time
- Multiple targets are fully independent — concurrent jobs do not interfere with each other

**Database — SQLite**
- Single file on the EC2 instance
- Stores snipe targets and credentials config
- Daily backup to S3

**SMS — Twilio**
- Sends notification on booking success or failure

**Hosting — EC2 t3.nano, us-east-1**
- ~$3.80/month
- Nginx reverse proxies `/api/*` to FastAPI (port 8000), serves React build at `/`
- FastAPI runs as a systemd service (auto-restart on crash, starts on boot)
- HTTPS via Let's Encrypt (Certbot)

---

## Resy API Integration

Authentication uses two values captured from browser network traffic and stored in the dashboard settings:
- `api_key` — Resy's app key (semi-static)
- `auth_token` — user's personal session token

Sent as: `Authorization: ResyKey apikey="...",auth_token="..."`

**Endpoints used:**
| Endpoint | Purpose |
|---|---|
| `GET /4/find` | Poll for available slots (venue + date + party size) |
| `POST /3/details` | Fetch `book_token` for a specific slot |
| `POST /3/book` | Execute the reservation |
| `GET /3/reservations` | Verify booking status on ambiguous outcome |

---

## Snipe Job Flow

Each target runs this flow independently:

```
T-5 min     Pre-warm HTTP keep-alive connection to api.resy.com

T=0:00      Begin polling GET /4/find
            - Every 1s for the first 60s (60 attempts)
            - Every 2s for the next 60s (30 attempts)
            - Stop after 2 minutes total; mark target as failed; send SMS

On slot found:
  1. POST /3/details  →  obtain book_token
  2. POST /3/book     →  execute reservation
  3. On timeout/network error: retry /3/book with the SAME book_token immediately
  4. On definitive success: mark target as booked; send SMS
  5. On definitive failure (token expired/invalid): mark as failed; send SMS
```

**Idempotency:**
- A `booking_in_flight` flag is set atomically when the first `/3/book` request fires
- No new `book_token` is acquired while this flag is set
- Retrying with the same `book_token` is safe — Resy's backend treats it as idempotent and will not charge twice
- A new token is only acquired if Resy explicitly returns an expired/invalid token error
- Target status transitions are one-way: `pending → sniping → booked | failed`

---

## Multiple Concurrent Targets

Each target is a separate APScheduler job with its own schedule, polling loop, and state. Example:

| Target | Date | Party | Opens |
|---|---|---|---|
| Carbone | June 15 | 2 | 9:00 AM |
| Le Bernardin | July 4 | 4 | 10:00 AM |
| Don Angie | June 20 | 2 | 9:00 AM |

Jobs fire independently. If two targets open at the same time, they run as concurrent async tasks — no resource contention since the workload is pure network I/O.

---

## Data Model

**`targets` table**
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| venue_id | TEXT | From Resy URL or network traffic |
| venue_name | TEXT | Display name |
| date | DATE | Target reservation date |
| party_size | INTEGER | |
| opening_time | DATETIME | When reservations become available |
| preferred_start | TIME | Optional — earliest acceptable slot time |
| preferred_end | TIME | Optional — latest acceptable slot time |
| status | TEXT | `pending`, `sniping`, `booked`, `failed` |
| booked_at | DATETIME | Populated on success |
| reservation_details | TEXT | JSON blob from Resy on success |

**`config` table**
| Column | Type | Notes |
|---|---|---|
| key | TEXT PK | |
| value | TEXT | |

Keys: `resy_api_key`, `resy_auth_token`, `twilio_account_sid`, `twilio_auth_token`, `twilio_from`, `phone_number`, `dashboard_api_key`

---

## Dashboard

**Targets view (main)**
- List all targets with status badges
- Add new target (venue ID, venue name, date, party size, opening time, optional preferred time window)
- Delete pending targets

**Settings view**
- Configure Resy credentials (`api_key`, `auth_token`)
- Configure Twilio credentials and phone number
- Set dashboard API key

---

## Security

- Dashboard protected by a static API key (set in `.env`, checked on every request)
- HTTPS enforced via Let's Encrypt — credentials never sent in plaintext
- Credentials stored in the `config` table, never in code or logs
- `.env` is gitignored

---

## Local Development

- FastAPI: `uvicorn main:app --reload` (port 8000)
- React: `vite dev` (port 5173)
- `.env` file for all credentials (never committed)
- SQLite file lives locally in the project root

---

## Out of Scope

- Multi-user support (single-user tool)
- Docker / containerization
- Browser automation (Playwright, Selenium) — direct API calls only
- Continuous background polling (bot is only active around opening times)
