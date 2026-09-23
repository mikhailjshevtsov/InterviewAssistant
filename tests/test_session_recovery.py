from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.callbacks import MenuAction, MenuCallback
from app.bot.handlers.start import (
    continue_session_callback,
    new_session_callback,
    start_handler,
)
from app.bot.states import InterviewState
from app.bot.texts import CONTINUE_SESSION_TEXT, VACANCY_PROMPT_TEXT
from app.database.models import InterviewSession, InterviewSessionStatus, Vacancy
from app.database.repositories.session_repository import InterviewSessionRepository
from app.services.interview_session_service import InterviewSessionService
from app.services.session_recovery_service import RecoveryScreen, SessionRecoveryService
from app.services.session_summary_service import SessionSummaryService
from app.services.user_service import UserService
from app.services.vacancy_service import VacancyService
from answer_helpers import (
    ANSWER_ANALYSIS,
    ANSWER_TEXT,
    QUESTIONS,
    SUMMARY,
    VACANCY_ANALYSIS,
    VACANCY_TEXT,
    add_analyzed_answer,
    create_session_with_questions,
)


CONTINUE = MenuCallback(action=MenuAction.CONTINUE_SESSION).pack()
NEW = MenuCallback(action=MenuAction.NEW_SESSION).pack()


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    return answer


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


def make_tg_message(text: str = "/start") -> Message:
    return Message(
        message_id=1, date=datetime.now(UTC), chat=Chat(id=1, type="private"), text=text
    )


def make_start_message() -> SimpleNamespace:
    return SimpleNamespace(
        text="/start",
        from_user=SimpleNamespace(id=1, username="john", full_name="John Doe"),
        answer=AsyncMock(),
    )


def make_callback() -> SimpleNamespace:
    return SimpleNamespace(message=make_tg_message(), answer=AsyncMock())


def callback_data_of(markup: InlineKeyboardMarkup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


async def start(
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    telegram_id: int = 1,
) -> SimpleNamespace:
    message = SimpleNamespace(
        text="/start",
        from_user=SimpleNamespace(id=telegram_id, username="john", full_name="John"),
        answer=AsyncMock(),
    )
    await start_handler(
        message,
        state,
        UserService(session_factory),
        SessionRecoveryService(session_factory),
    )
    return message


async def test_no_active_session(session_factory: async_sessionmaker[AsyncSession]) -> None:
    user = await UserService(session_factory).get_or_create_user(1, None, None)

    assert await InterviewSessionService(session_factory).get_active_session(user.id) is None
    assert await SessionRecoveryService(session_factory).build(user.id) is None


async def test_active_session_is_the_latest(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first = await create_session_with_questions(session_factory)
    second = await create_session_with_questions(session_factory)
    user = await UserService(session_factory).get_or_create_user(1, None, None)
    await InterviewSessionService(session_factory).update_status(
        first, InterviewSessionStatus.SUMMARY_RESULT
    )

    active = await InterviewSessionService(session_factory).get_active_session(user.id)
    recovery = await SessionRecoveryService(session_factory).build(user.id)

    assert active is not None and active.id == second
    assert recovery is not None and recovery.session_id == second
    assert recovery.screen is RecoveryScreen.QUESTIONS


async def test_completed_older_session_is_not_active(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    older = await create_session_with_questions(session_factory)
    await InterviewSessionService(session_factory).update_status(
        older, InterviewSessionStatus.SUMMARY_RESULT
    )
    newer = await create_session_with_questions(session_factory)
    user = await UserService(session_factory).get_or_create_user(1, None, None)

    active = await InterviewSessionService(session_factory).get_active_session(user.id)

    assert active is not None and active.id == newer != older


async def test_recover_after_vacancy_analysis(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await UserService(session_factory).get_or_create_user(1, None, None)
    vacancy = await VacancyService(session_factory).create(user.id, VACANCY_TEXT)
    interview = await InterviewSessionService(session_factory).start_vacancy_analysis(
        user.id, vacancy.id
    )
    await InterviewSessionService(session_factory).mark_vacancy_result(interview.id)
    async with session_factory() as session:
        from app.database.repositories.vacancy_repository import VacancyRepository

        await VacancyRepository(session).save_analysis(
            vacancy.id, VACANCY_ANALYSIS.position, VACANCY_ANALYSIS.model_dump_json()
        )
        await session.commit()

    recovery = await SessionRecoveryService(session_factory).build(user.id)

    assert recovery is not None
    assert recovery.screen is RecoveryScreen.VACANCY_RESULT
    assert recovery.vacancy_analysis == VACANCY_ANALYSIS
    assert recovery.session_id == interview.id


async def test_recover_unfinished_vacancy_analysis(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await UserService(session_factory).get_or_create_user(1, None, None)
    vacancy = await VacancyService(session_factory).create(user.id, VACANCY_TEXT)
    await InterviewSessionService(session_factory).start_vacancy_analysis(user.id, vacancy.id)

    recovery = await SessionRecoveryService(session_factory).build(user.id)

    assert recovery is not None
    assert recovery.screen is RecoveryScreen.VACANCY_INPUT


async def test_recover_questions_after_restart(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session_with_questions(session_factory)
    user = await UserService(session_factory).get_or_create_user(1, None, None)

    recovery = await SessionRecoveryService(session_factory).build(user.id)

    assert recovery is not None
    assert recovery.screen is RecoveryScreen.QUESTIONS
    assert recovery.session_id == session_id
    assert [question.id for question in recovery.questions] == ["Q-01", "Q-02", "Q-03"]


async def test_recover_saved_answer(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session_with_questions(session_factory)
    await add_analyzed_answer(session_factory, session_id, "Q-02")
    await InterviewSessionService(session_factory).update_status(
        session_id, InterviewSessionStatus.ANSWER_RESULT
    )
    user = await UserService(session_factory).get_or_create_user(1, None, None)

    recovery = await SessionRecoveryService(session_factory).build(user.id)

    assert recovery is not None
    assert recovery.screen is RecoveryScreen.ANSWER_RESULT
    assert recovery.question_id == "Q-02"
    assert recovery.answer_analysis == ANSWER_ANALYSIS


async def test_recover_cached_summary_without_openai(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session_with_questions(session_factory)
    await add_analyzed_answer(session_factory, session_id, "Q-01")
    cached_summary = SUMMARY.model_copy(
        update={
            "position": VACANCY_ANALYSIS.position,
            "answered_questions": 1,
            "total_questions": 3,
            "average_score": 7.0,
            "star_statistics": None,
        }
    )
    async with session_factory() as session:
        repository = InterviewSessionRepository(session)
        await repository.save_summary(session_id, cached_summary.model_dump_json())
        await repository.update_status(session_id, InterviewSessionStatus.SUMMARY_RESULT)
        await session.commit()
    user = await UserService(session_factory).get_or_create_user(1, None, None)
    llm = SimpleNamespace(summarize_session=AsyncMock())

    recovery = await SessionRecoveryService(session_factory).build(user.id)
    cached = await SessionSummaryService(llm, session_factory).get_saved_summary(session_id)

    assert recovery is not None
    assert recovery.screen is RecoveryScreen.SUMMARY_RESULT
    assert recovery.summary == cached_summary
    assert cached == cached_summary
    llm.summarize_session.assert_not_awaited()


async def test_new_session_does_not_delete_old(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first = await create_session_with_questions(session_factory)
    user = await UserService(session_factory).get_or_create_user(1, None, None)
    vacancy = await VacancyService(session_factory).create(user.id, VACANCY_TEXT)
    second = await InterviewSessionService(session_factory).start_vacancy_analysis(
        user.id, vacancy.id
    )

    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(InterviewSession))
        first_row = await session.get(InterviewSession, first)

    assert count == 2
    assert second.id != first
    assert first_row is not None
    assert first_row.status == InterviewSessionStatus.QUESTIONS


async def test_start_after_clear_fsm_offers_continue(
    state: FSMContext, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    session_id = await create_session_with_questions(session_factory)
    await state.update_data(session_id=session_id, question_id="Q-01")
    await state.clear()

    message = await start(state, session_factory)

    assert await state.get_state() == InterviewState.MAIN_MENU.state
    assert message.answer.await_args.args[0] == CONTINUE_SESSION_TEXT
    assert CONTINUE in callback_data_of(message.answer.await_args.kwargs["reply_markup"])
    assert NEW in callback_data_of(message.answer.await_args.kwargs["reply_markup"])


async def test_continue_restores_questions_without_new_session(
    state: FSMContext,
    sent: AsyncMock,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session_with_questions(session_factory)
    await start(state, session_factory)
    async with session_factory() as session:
        before = await session.scalar(select(func.count()).select_from(InterviewSession))
    callback = make_callback()

    await continue_session_callback(callback, state, SessionRecoveryService(session_factory))

    assert await state.get_state() == InterviewState.QUESTIONS.state
    data = await state.get_data()
    assert data["session_id"] == session_id
    assert "Q-01" in sent.await_args.args[0] or "SQL JOIN" in sent.await_args.args[0]
    async with session_factory() as session:
        after = await session.scalar(select(func.count()).select_from(InterviewSession))
    assert after == before == 1


async def test_continue_restores_answer_and_allows_retry_data(
    state: FSMContext,
    sent: AsyncMock,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session_with_questions(session_factory)
    await add_analyzed_answer(session_factory, session_id, "Q-02", ANSWER_ANALYSIS, ANSWER_TEXT)
    await InterviewSessionService(session_factory).update_status(
        session_id, InterviewSessionStatus.ANSWER_RESULT
    )
    await start(state, session_factory)

    await continue_session_callback(
        make_callback(), state, SessionRecoveryService(session_factory)
    )

    assert await state.get_state() == InterviewState.NEXT_ACTION.state
    assert (await state.get_data())["question_id"] == "Q-02"
    assert "📊 Оценка: 7/10" in sent.await_args.args[0]


async def test_new_session_keeps_old_row(
    state: FSMContext,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session_with_questions(session_factory)
    await start(state, session_factory)
    edit = AsyncMock()
    monkeypatch.setattr(Message, "edit_text", edit)

    await new_session_callback(make_callback(), state)

    assert await state.get_state() == InterviewState.WAITING_VACANCY.state
    assert set((await state.get_data())) == {"user_id"}
    edit.assert_awaited_once()
    assert edit.await_args.args[0] == VACANCY_PROMPT_TEXT
    async with session_factory() as session:
        assert await session.get(InterviewSession, session_id) is not None
        assert await session.scalar(select(func.count()).select_from(InterviewSession)) == 1


async def test_existing_data_survives_init_db(
    session_factory: async_sessionmaker[AsyncSession],
    engine,
) -> None:
    from app.database.database import init_db

    session_id = await create_session_with_questions(session_factory)
    await add_analyzed_answer(session_factory, session_id, "Q-01")
    async with session_factory() as session:
        await InterviewSessionRepository(session).save_summary(
            session_id, SUMMARY.model_dump_json()
        )
        await session.commit()
        user_count = await session.scalar(select(func.count()).select_from(Vacancy))

    await init_db(engine)

    async with session_factory() as session:
        interview = await session.get(InterviewSession, session_id)
        vacancy = await session.get(Vacancy, interview.vacancy_id)
        from app.database.models import Answer, SessionQuestion, User

        assert await session.scalar(select(func.count()).select_from(User)) == 1
        assert user_count == 1
        assert vacancy is not None and vacancy.analysis_json is not None
        assert vacancy.text
        questions = await session.scalars(
            select(SessionQuestion).where(SessionQuestion.session_id == session_id)
        )
        answers = await session.scalars(select(Answer).where(Answer.session_id == session_id))
        assert len(list(questions)) == 3
        assert len(list(answers)) == 1
        assert interview.summary_json == SUMMARY.model_dump_json()
