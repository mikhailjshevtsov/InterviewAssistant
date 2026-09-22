from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.handlers.start import start_handler
from app.bot.handlers.vacancy import vacancy_received
from app.bot.states import InterviewState
from app.bot.texts import DATABASE_ERROR_TEXT
from app.database.exceptions import DatabaseError
from app.database.models import InterviewSession, InterviewSessionStatus, User, Vacancy
from app.services.interview_session_service import InterviewSessionService
from app.services.user_service import UserService
from app.services.vacancy_service import VacancyService

VACANCY_TEXT = "Python backend developer. " * 10


def make_message(text: str | None = "/start") -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=100500, username="john", full_name="John Doe"),
        answer=AsyncMock(),
    )


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1)
    )


@pytest.fixture
def services(session_factory: async_sessionmaker[AsyncSession]) -> dict:
    return {
        "user_service": UserService(session_factory),
        "vacancy_service": VacancyService(session_factory),
        "interview_session_service": InterviewSessionService(session_factory),
    }


async def test_start_and_vacancy_flow_persists_and_fills_fsm(
    state: FSMContext,
    services: dict,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await state.update_data(vacancy_id=1, session_id=1)
    await start_handler(make_message(), state, services["user_service"])
    await start_handler(make_message(), state, services["user_service"])

    data = await state.get_data()
    assert await state.get_state() == InterviewState.MAIN_MENU.state
    assert set(data) == {"user_id"}

    await state.set_state(InterviewState.WAITING_VACANCY)
    await vacancy_received(make_message(VACANCY_TEXT), state, **services)

    data = await state.get_data()
    assert await state.get_state() == InterviewState.ANALYZING_VACANCY.state
    assert {"user_id", "vacancy_id", "session_id"} <= set(data)

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        vacancy = await session.get(Vacancy, data["vacancy_id"])
        interview_session = await session.get(InterviewSession, data["session_id"])

    assert vacancy is not None and vacancy.user_id == data["user_id"]
    assert interview_session is not None
    assert interview_session.vacancy_id == vacancy.id
    assert interview_session.status == InterviewSessionStatus.ANALYZING_VACANCY


async def test_invalid_vacancy_is_not_saved(
    state: FSMContext,
    services: dict,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await start_handler(make_message(), state, services["user_service"])
    await state.set_state(InterviewState.WAITING_VACANCY)
    await vacancy_received(make_message("too short"), state, **services)

    assert await state.get_state() == InterviewState.WAITING_VACANCY.state
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Vacancy)) == 0


async def test_database_error_is_shown_without_traceback(state: FSMContext) -> None:
    user_service = SimpleNamespace(
        get_or_create_user=AsyncMock(side_effect=DatabaseError("db down"))
    )
    message = make_message()

    await start_handler(message, state, user_service)

    message.answer.assert_awaited_once_with(DATABASE_ERROR_TEXT)
    assert await state.get_state() is None
