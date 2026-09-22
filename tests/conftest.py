import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

# Must run before any `app` import: settings and the global engine are created at import time.
os.environ.setdefault("BOT_TOKEN", "123456:TEST")
os.environ["DATABASE_URL"] = (
    f"sqlite+aiosqlite:///{Path(tempfile.gettempdir()) / 'interview_assistant_unused.db'}"
)

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.database.database import create_engine, create_session_factory, init_db


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'data' / 'test.db'}"


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    test_engine = create_engine(database_url)
    await init_db(test_engine)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)
