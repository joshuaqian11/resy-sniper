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
            if "timeout" in str(e).lower():
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
