from pathlib import Path
from typing import Any

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import URL, Connection
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


# create_all never alters existing tables, so columns added after a table was first
# created are listed here until Alembic is introduced.
ADDED_COLUMNS: tuple[tuple[str, str, str, bool], ...] = (
    (
        "answers",
        "session_question_id",
        "INTEGER REFERENCES interview_questions(id) ON DELETE CASCADE",
        True,
    ),
    ("interview_sessions", "summary_json", "TEXT", False),
)


def _add_missing_columns(connection: Connection) -> None:
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())
    for table, column, ddl, indexed in ADDED_COLUMNS:
        if table not in existing_tables:
            continue
        if column in {info["name"] for info in inspector.get_columns(table)}:
            continue
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        if indexed:
            connection.execute(
                text(f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} ON {table} ({column})")
            )


async def init_db(target_engine: AsyncEngine | None = None) -> None:
    target_engine = target_engine or engine
    _ensure_sqlite_directory(target_engine.url)
    async with target_engine.begin() as connection:
        await connection.run_sync(_add_missing_columns)
        await connection.run_sync(Base.metadata.create_all)
