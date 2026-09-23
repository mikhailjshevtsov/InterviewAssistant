from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.database.database import create_engine, create_session_factory, init_db
from app.database.exceptions import DatabaseError
from app.database.models import InterviewSessionStatus, User
from app.database.repositories import (
    AnswerRepository,
    InterviewSessionRepository,
    UserRepository,
    VacancyRepository,
)
from app.services.interview_session_service import InterviewSessionService
from app.services.user_service import UserService
from app.services.vacancy_service import VacancyService

VACANCY_TEXT = "Python backend developer. " * 10


async def test_init_db_creates_all_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "data" / "init.db"
    test_engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    try:
        await init_db(test_engine)
        async with test_engine.connect() as connection:
            tables = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_table_names()
            )
    finally:
        await test_engine.dispose()

    assert database_path.exists()
    assert {"users", "vacancies", "interview_sessions", "answers"} <= set(tables)


async def test_user_is_created(session_factory: async_sessionmaker[AsyncSession]) -> None:
    user = await UserService(session_factory).get_or_create_user(42, "john", "John Doe")

    assert user.id is not None
    assert user.telegram_id == 42
    assert user.username == "john"
    assert user.full_name == "John Doe"
    assert user.created_at is not None


async def test_get_or_create_does_not_duplicate_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = UserService(session_factory)
    first = await service.get_or_create_user(42, "john", "John Doe")
    second = await service.get_or_create_user(42, "john", "John Doe")

    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(User))

    assert first.id == second.id
    assert count == 1


async def test_vacancy_is_created_and_linked_to_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await UserService(session_factory).get_or_create_user(1, None, None)
    vacancy = await VacancyService(session_factory).create(user.id, VACANCY_TEXT)

    assert vacancy.id is not None
    assert vacancy.user_id == user.id
    assert vacancy.text == VACANCY_TEXT
    assert vacancy.position is None
    assert vacancy.analysis_json is None

    async with session_factory() as session:
        db_user = await session.get(User, user.id)
        assert db_user is not None
        await session.refresh(db_user, ["vacancies"])
        assert [v.id for v in db_user.vacancies] == [vacancy.id]


async def test_interview_session_is_created_and_linked(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await UserService(session_factory).get_or_create_user(1, None, None)
    vacancy = await VacancyService(session_factory).create(user.id, VACANCY_TEXT)
    service = InterviewSessionService(session_factory)
    interview_session = await service.create(
        user.id, vacancy.id, InterviewSessionStatus.ANALYZING_VACANCY
    )

    assert interview_session.id is not None
    assert interview_session.status == InterviewSessionStatus.ANALYZING_VACANCY

    async with session_factory() as session:
        repository = InterviewSessionRepository(session)
        loaded = await repository.get_by_id(interview_session.id)
        assert loaded is not None
        await session.refresh(loaded, ["user", "vacancy"])
        assert loaded.user.id == user.id
        assert loaded.vacancy.id == vacancy.id

    updated = await service.update_status(
        interview_session.id, InterviewSessionStatus.VACANCY_RESULT
    )
    assert updated.status == InterviewSessionStatus.VACANCY_RESULT


async def test_answer_is_created_and_analysis_saved(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await UserRepository(session).create(1, None, None)
        vacancy = await VacancyRepository(session).create(user.id, VACANCY_TEXT)
        interview_session = await InterviewSessionRepository(session).create(
            user.id, vacancy.id, InterviewSessionStatus.WAITING_ANSWER
        )
        answer = await AnswerRepository(session).create(
            interview_session.id, "Tell me about yourself", "I am a developer"
        )
        await session.commit()
        answer_id = answer.id

    assert answer.ai_analysis is None
    assert answer.score is None

    async with session_factory() as session:
        await AnswerRepository(session).save_analysis(answer_id, "Good answer", 8)
        await session.commit()

    async with session_factory() as session:
        saved = await AnswerRepository(session).get_by_id(answer_id)
        assert saved is not None
        assert saved.session_id == interview_session.id
        assert saved.ai_analysis == "Good answer"
        assert saved.score == 8


async def test_vacancy_save_analysis(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await UserService(session_factory).get_or_create_user(1, None, None)
    vacancy = await VacancyService(session_factory).create(user.id, VACANCY_TEXT)

    async with session_factory() as session:
        await VacancyRepository(session).save_analysis(
            vacancy.id, "Python Developer", '{"skills": ["python"]}'
        )
        await session.commit()

    async with session_factory() as session:
        saved = await VacancyRepository(session).get_by_id(vacancy.id)
        assert saved is not None
        assert saved.position == "Python Developer"
        assert saved.analysis_json == '{"skills": ["python"]}'


async def test_foreign_keys_are_enforced(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        with pytest.raises(IntegrityError):
            await VacancyRepository(session).create(user_id=999, text=VACANCY_TEXT)
        await session.rollback()

    async with session_factory() as session:
        with pytest.raises(IntegrityError):
            await AnswerRepository(session).create(999, "question", "answer")
        await session.rollback()


async def test_service_wraps_errors_and_rolls_back(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(DatabaseError):
        await VacancyService(session_factory).create(user_id=999, vacancy_text=VACANCY_TEXT)

    user = await UserService(session_factory).get_or_create_user(1, None, None)
    vacancy = await VacancyService(session_factory).create(user.id, VACANCY_TEXT)
    assert vacancy.id is not None


async def test_data_persists_after_engine_restart(database_url: str) -> None:
    first_engine = create_engine(database_url)
    await init_db(first_engine)
    user = await UserService(create_session_factory(first_engine)).get_or_create_user(
        7, "persisted", None
    )
    await first_engine.dispose()

    second_engine = create_engine(database_url)
    try:
        await init_db(second_engine)
        async with create_session_factory(second_engine)() as session:
            loaded = await UserRepository(session).get_by_telegram_id(7)
    finally:
        await second_engine.dispose()

    assert loaded is not None
    assert loaded.id == user.id
    assert loaded.username == "persisted"


async def test_engine_fixture_uses_test_database(engine: AsyncEngine) -> None:
    assert "app.db" not in str(engine.url)


async def test_init_db_adds_answer_link_to_existing_database(tmp_path: Path) -> None:
    from sqlalchemy import text

    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "CREATE TABLE answers (id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, "
                "question TEXT NOT NULL, user_answer TEXT NOT NULL, ai_analysis TEXT, "
                "score INTEGER, created_at DATETIME)"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO answers (session_id, question, user_answer) "
                "VALUES (1, 'old question', 'old answer')"
            )
        )

    await init_db(engine)
    await init_db(engine)

    async with engine.connect() as connection:
        columns, indexes = await connection.run_sync(
            lambda sync: (
                {column["name"] for column in inspect(sync).get_columns("answers")},
                {index["name"] for index in inspect(sync).get_indexes("answers")},
            )
        )
        rows = (await connection.execute(text("SELECT user_answer FROM answers"))).all()
    await engine.dispose()

    assert "session_question_id" in columns
    assert "ix_answers_session_question_id" in indexes
    assert rows == [("old answer",)]
