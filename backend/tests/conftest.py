import pytest
import pytest_asyncio
from database import Database

@pytest_asyncio.fixture
async def tmp_db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    await db.init()
    yield db
    await db.close()
