from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.database.models import Base


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_engine(database_url: str) -> AsyncEngine:
    new_engine = create_async_engine(database_url)
    if new_engine.dialect.name == "sqlite":
        # SQLite ignores foreign keys unless enabled on every connection.
        event.listen(new_engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    return new_engine


def create_session_factory(bind: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=bind, expire_on_commit=False)


def _ensure_sqlite_directory(url: URL) -> None:
    if url.get_backend_name() != "sqlite":
        return
    database = url.database
    if not database or database == ":memory:":
        return
    Path(database).parent.mkdir(parents=True, exist_ok=True)


engine = create_engine(settings.database_url)
AsyncSessionFactory = create_session_factory(engine)


async def init_db(target_engine: AsyncEngine | None = None) -> None:
    target_engine = target_engine or engine
    _ensure_sqlite_directory(target_engine.url)
    async with target_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
