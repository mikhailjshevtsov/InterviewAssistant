from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.formatters import TELEGRAM_MESSAGE_LIMIT, format_vacancy_analysis
from app.bot.handlers.vacancy import vacancy_received
from app.bot.states import InterviewState
from app.bot.texts import DATABASE_ERROR_TEXT, LLM_ERROR_TEXT
from app.database.database import create_engine, create_session_factory, init_db
from app.database.exceptions import DatabaseError, EntityNotFoundError
from app.database.models import InterviewSession, InterviewSessionStatus, Vacancy
from app.database.repositories import VacancyRepository
from app.schemas.vacancy import VacancyAnalysis
from app.services.exceptions import InvalidVacancyTextError, LLMServiceError
from app.services.interview_session_service import InterviewSessionService
from app.services.user_service import UserService
from app.services.vacancy_service import VacancyService
from app.services.vacancy_validator import VacancyValidationError

VACANCY_TEXT = "Ищем бизнес-аналитика: SQL, BPMN, REST API, сбор требований. " * 3
ANALYSIS = VacancyAnalysis(
    position="Бизнес-аналитик",
    company="ABC",
    hard_skills=["SQL", "BPMN"],
    interview_topics=["SQL"],
)


def make_llm(**kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(analyze_vacancy=AsyncMock(**kwargs))


async def create_vacancy(
    session_factory: async_sessionmaker[AsyncSession], text: str = VACANCY_TEXT
) -> int:
    user = await UserService(session_factory).get_or_create_user(1, None, None)
    vacancy = await VacancyService(session_factory).create(user.id, text)
    return vacancy.id


async def insert_raw_vacancy(
    session_factory: async_sessionmaker[AsyncSession], text: str
) -> int:
    user = await UserService(session_factory).get_or_create_user(1, None, None)
    async with session_factory() as session:
        vacancy = await VacancyRepository(session).create(user.id, text)
        await session.commit()
        await session.refresh(vacancy)
    return vacancy.id


async def load_vacancy(session_factory: async_sessionmaker[AsyncSession], vacancy_id: int):
    async with session_factory() as session:
        return await VacancyRepository(session).get_by_id(vacancy_id)


async def test_analysis_is_saved_to_database(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    vacancy_id = await create_vacancy(session_factory)
    llm = make_llm(return_value=ANALYSIS)

    result = await VacancyService(session_factory, llm=llm).analyze(vacancy_id)

    assert isinstance(result, VacancyAnalysis)
    llm.analyze_vacancy.assert_awaited_once_with(VACANCY_TEXT.strip())
    vacancy = await load_vacancy(session_factory, vacancy_id)
    assert vacancy.analysis_json is not None
    assert vacancy.position == "Бизнес-аналитик"
    assert VacancyAnalysis.model_validate_json(vacancy.analysis_json) == ANALYSIS


@pytest.mark.parametrize(
    "text",
    ["", "   \n\t ", "Python developer"],
)
async def test_create_rejects_invalid_vacancy(
    session_factory: async_sessionmaker[AsyncSession],
    text: str,
) -> None:
    user = await UserService(session_factory).get_or_create_user(1, None, None)

    with pytest.raises(InvalidVacancyTextError):
        await VacancyService(session_factory).create(user.id, text)

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Vacancy)) == 0


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("", VacancyValidationError.EMPTY),
        ("   \n\t ", VacancyValidationError.EMPTY),
        ("Python developer", VacancyValidationError.TOO_SHORT),
    ],
)
async def test_invalid_vacancy_does_not_call_llm(
    session_factory: async_sessionmaker[AsyncSession],
    text: str,
    error: VacancyValidationError,
) -> None:
    vacancy_id = await insert_raw_vacancy(session_factory, text)
    llm = make_llm(return_value=ANALYSIS)

    with pytest.raises(InvalidVacancyTextError) as exc_info:
        await VacancyService(session_factory, llm=llm).analyze(vacancy_id)

    assert exc_info.value.error is error
    llm.analyze_vacancy.assert_not_awaited()
    assert (await load_vacancy(session_factory, vacancy_id)).analysis_json is None


async def test_missing_vacancy_does_not_call_llm(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    llm = make_llm(return_value=ANALYSIS)

    with pytest.raises(EntityNotFoundError):
        await VacancyService(session_factory, llm=llm).analyze(999)

    llm.analyze_vacancy.assert_not_awaited()


async def test_llm_error_leaves_no_partial_analysis(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    vacancy_id = await create_vacancy(session_factory)
    llm = make_llm(side_effect=LLMServiceError("OpenAI request failed: timeout"))

    with pytest.raises(LLMServiceError):
        await VacancyService(session_factory, llm=llm).analyze(vacancy_id)

    vacancy = await load_vacancy(session_factory, vacancy_id)
    assert vacancy.analysis_json is None
    assert vacancy.position is None


async def test_save_failure_rolls_back_and_raises_database_error(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vacancy_id = await create_vacancy(session_factory)
    original_save = VacancyRepository.save_analysis

    async def failing_save(self: VacancyRepository, *args: object, **kwargs: object):
        await original_save(self, *args, **kwargs)
        raise OperationalError("UPDATE vacancies", {}, Exception("disk I/O error"))

    monkeypatch.setattr(VacancyRepository, "save_analysis", failing_save)

    with pytest.raises(DatabaseError):
        await VacancyService(session_factory, llm=make_llm(return_value=ANALYSIS)).analyze(
            vacancy_id
        )

    monkeypatch.setattr(VacancyRepository, "save_analysis", original_save)
    assert (await load_vacancy(session_factory, vacancy_id)).analysis_json is None


async def test_analysis_persists_after_restart(database_url: str) -> None:
    first_engine = create_engine(database_url)
    await init_db(first_engine)
    first_factory = create_session_factory(first_engine)
    vacancy_id = await create_vacancy(first_factory)
    await VacancyService(first_factory, llm=make_llm(return_value=ANALYSIS)).analyze(
        vacancy_id
    )
    await first_engine.dispose()

    second_engine = create_engine(database_url)
    try:
        vacancy = await load_vacancy(create_session_factory(second_engine), vacancy_id)
    finally:
        await second_engine.dispose()

    assert vacancy.analysis_json is not None
    assert VacancyAnalysis.model_validate_json(vacancy.analysis_json) == ANALYSIS


def make_message(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=100500, username="john", full_name="John Doe"),
        answer=AsyncMock(),
    )


async def run_vacancy_handler(
    session_factory: async_sessionmaker[AsyncSession], llm: SimpleNamespace
) -> tuple[FSMContext, SimpleNamespace]:
    state = FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1)
    )
    await state.set_state(InterviewState.WAITING_VACANCY)
    message = make_message(VACANCY_TEXT)
    await vacancy_received(
        message,
        state,
        user_service=UserService(session_factory),
        vacancy_service=VacancyService(session_factory, llm=llm),
        interview_session_service=InterviewSessionService(session_factory),
    )
    return state, message


async def test_handler_shows_formatted_result(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    state, message = await run_vacancy_handler(
        session_factory, make_llm(return_value=ANALYSIS)
    )

    assert await state.get_state() == InterviewState.VACANCY_RESULT.state
    assert message.answer.await_args.args[0] == format_vacancy_analysis(ANALYSIS)


@pytest.mark.parametrize(
    ("error", "expected_text"),
    [
        (LLMServiceError("OpenAI request failed: timeout"), LLM_ERROR_TEXT),
        (DatabaseError("Failed to save vacancy analysis"), DATABASE_ERROR_TEXT),
    ],
)
async def test_handler_error_does_not_mark_session_successful(
    session_factory: async_sessionmaker[AsyncSession],
    error: Exception,
    expected_text: str,
) -> None:
    state, message = await run_vacancy_handler(session_factory, make_llm(side_effect=error))

    assert await state.get_state() == InterviewState.WAITING_VACANCY.state
    assert message.answer.await_args.args[0] == expected_text
    async with session_factory() as session:
        interview_session = await session.get(
            InterviewSession, (await state.get_data())["session_id"]
        )
    assert interview_session.status == InterviewSessionStatus.ANALYZING_VACANCY


def test_formatter_output() -> None:
    text = format_vacancy_analysis(ANALYSIS)

    assert text.startswith("🎯 Анализ вакансии")
    assert "Позиция:\nБизнес-аналитик" in text
    assert "Компания:\nABC" in text
    assert "Hard skills:\n• SQL\n• BPMN" in text
    assert "Soft skills:\nне указано" in text
    assert "Темы для подготовки:\n• SQL" in text


def test_formatter_respects_telegram_limit() -> None:
    huge = VacancyAnalysis(position=None, company=None, hard_skills=["x" * 100] * 100)

    text = format_vacancy_analysis(huge)

    assert len(text) <= TELEGRAM_MESSAGE_LIMIT
    assert "Позиция:\nне указано" in text
