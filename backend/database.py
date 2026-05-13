import json
import aiosqlite
from datetime import datetime, timezone
from typing import Optional

class Database:
    def __init__(self, path: str):
        self.path = path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self):
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()

    async def close(self):
        if self._db:
            await self._db.close()

    async def _create_tables(self):
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_id TEXT NOT NULL,
                venue_name TEXT NOT NULL,
                date TEXT NOT NULL,
                party_size INTEGER NOT NULL,
                opening_time TEXT NOT NULL,
                preferred_start TEXT,
                preferred_end TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                booked_at TEXT,
                reservation_details TEXT
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await self._db.commit()

    async def execute_fetchall(self, sql: str, params=()) -> list[dict]:
        async with self._db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def insert_target(self, t: dict) -> int:
        async with self._db.execute(
            """INSERT INTO targets
               (venue_id, venue_name, date, party_size, opening_time,
                preferred_start, preferred_end, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (t["venue_id"], t["venue_name"], t["date"], t["party_size"],
             t["opening_time"], t.get("preferred_start"), t.get("preferred_end"))
        ) as cursor:
            await self._db.commit()
            return cursor.lastrowid

    async def get_all_targets(self) -> list[dict]:
        return await self.execute_fetchall(
            "SELECT * FROM targets ORDER BY opening_time"
        )

    async def get_pending_targets(self) -> list[dict]:
        return await self.execute_fetchall(
            "SELECT * FROM targets WHERE status = 'pending' ORDER BY opening_time"
        )

    async def get_target(self, target_id: int) -> Optional[dict]:
        rows = await self.execute_fetchall(
            "SELECT * FROM targets WHERE id = ?", (target_id,)
        )
        return rows[0] if rows else None

    async def update_target_status(self, target_id: int, status: str):
        await self._db.execute(
            "UPDATE targets SET status = ? WHERE id = ?", (status, target_id)
        )
        await self._db.commit()

    async def update_target_booked(self, target_id: int, reservation_details: dict):
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """UPDATE targets
               SET status = 'booked', booked_at = ?, reservation_details = ?
               WHERE id = ?""",
            (now, json.dumps(reservation_details), target_id)
        )
        await self._db.commit()

    async def delete_target_if_pending(self, target_id: int) -> bool:
        async with self._db.execute(
            "DELETE FROM targets WHERE id = ? AND status = 'pending'", (target_id,)
        ) as cursor:
            await self._db.commit()
            return cursor.rowcount > 0

    async def set_config(self, key: str, value: str):
        await self._db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value)
        )
        await self._db.commit()

    async def get_config(self, key: str) -> Optional[str]:
        rows = await self.execute_fetchall(
            "SELECT value FROM config WHERE key = ?", (key,)
        )
        return rows[0]["value"] if rows else None

    async def get_all_config(self) -> dict[str, str]:
        rows = await self.execute_fetchall("SELECT key, value FROM config")
        return {r["key"]: r["value"] for r in rows}
