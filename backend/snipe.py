import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Configurable for testing
PHASE1_DURATION = 60.0   # seconds — poll every 1s
PHASE2_DURATION = 60.0   # seconds — poll every 2s
PHASE1_INTERVAL = 1.0
PHASE2_INTERVAL = 2.0

def filter_slots(slots: list[dict], preferred_start: str | None, preferred_end: str | None) -> list[dict]:
    if not preferred_start and not preferred_end:
        return slots
    result = []
    for slot in slots:
        slot_time_str = slot["date"]["start"].split(" ")[1][:5]  # "HH:MM"
        if preferred_start and slot_time_str < preferred_start:
            continue
        if preferred_end and slot_time_str > preferred_end:
            continue
        result.append(slot)
    return result

async def _book_with_retry(resy_client, book_token: str) -> dict:
    """Retry booking with the same book_token on timeout. Raises on terminal errors."""
    while True:
        try:
            return await resy_client.book(book_token)
        except TimeoutError:
            logger.warning("Book request timed out — retrying with same token")
            continue

async def run_snipe(target: dict, resy_client, sms_client, db) -> None:
    target_id = target["id"]
    venue_name = target["venue_name"]
    venue_id = target["venue_id"]
    date = target["date"]
    party_size = target["party_size"]
    preferred_start = target.get("preferred_start")
    preferred_end = target.get("preferred_end")

    await db.update_target_status(target_id, "sniping")
    logger.info(f"[{venue_name}] Snipe started — venue_id={venue_id!r} date={date!r} party_size={party_size}")

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
            await db.update_target_booked(target_id, result)
            sms_client.send(f"Booked {venue_name} on {date} for {party_size}!")
            logger.info(f"[{venue_name}] Booked successfully")
        except Exception as e:
            err = str(e)
            if "invalid book token" in err.lower():
                # Slot was taken between get_book_token and book — release lock so
                # the poll loop can immediately try a fresh slot on the next tick
                logger.warning(f"[{venue_name}] Book token invalidated (slot taken) — retrying next poll")
                booking_in_flight = False
            else:
                logger.error(f"[{venue_name}] Booking failed: {e}")
                await db.update_target_status(target_id, "failed")
                sms_client.send(f"Failed to book {venue_name} on {date}: {e}")
        finally:
            if not booked:
                booking_in_flight = False

    loop = asyncio.get_running_loop()

    async def poll(interval: float, duration: float):
        deadline = loop.time() + duration
        while loop.time() < deadline and not booked:
            try:
                slots = await resy_client.find_slots(venue_id, date, party_size)
                logger.debug(f"[{venue_name}] find_slots returned {len(slots)} slot(s)")
                matching = filter_slots(slots, preferred_start, preferred_end)
                if matching and not booking_in_flight and not booked:
                    asyncio.ensure_future(attempt_booking(matching[0]))
            except Exception as e:
                logger.warning(f"[{venue_name}] find_slots error (venue_id={venue_id!r}, date={date!r}): {e}")
            await asyncio.sleep(interval)

    await poll(PHASE1_INTERVAL, PHASE1_DURATION)
    if not booked:
        await poll(PHASE2_INTERVAL, PHASE2_DURATION)

    if not booked and not booking_in_flight:
        await db.update_target_status(target_id, "failed")
        sms_client.send(f"Failed to book {venue_name} on {date} — no slots found in 2 minute window")
        logger.warning(f"[{venue_name}] Snipe window expired with no booking")
