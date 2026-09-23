from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.callbacks import MenuAction, MenuCallback
from app.bot.handlers.summary import (
    generating_summary_message,
    session_summary_callback,
    summary_result_message,
)
from app.bot.keyboards import questions_keyboard
from app.bot.states import InterviewState
from app.bot.texts import (
    GENERATING_SUMMARY_TEXT,
    SUMMARY_IN_PROGRESS_TEXT,
    SUMMARY_LLM_ERROR_TEXT,
    SUMMARY_NO_ANSWERS_TEXT,
    SUMMARY_RESULT_HINT_TEXT,
)
from app.schemas.session_summary import InterviewSummary
from app.services.exceptions import LLMServiceError
from app.services.session_summary_service import SessionSummaryService
from answer_helpers import (
    SUMMARY,
    add_analyzed_answer,
    analysis_with_score,
    create_session_with_questions,
    make_questions,
)

SUMMARY_CALLBACK = MenuCallback(action=MenuAction.SESSION_SUMMARY).pack()
BACK = MenuCallback(action=MenuAction.BACK_QUESTIONS).pack()
MAIN = MenuCallback(action=MenuAction.MAIN_MENU).pack()


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    return answer


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


class FakeLLM:
    def __init__(self, state: FSMContext, error: Exception | None = None):
        self.state = state
        self.error = error
        self.calls = 0
        self.states_during_call: list[str | None] = []

    async def summarize_session(self, vacancy_analysis, answered, statistics) -> InterviewSummary:
        self.calls += 1
        self.states_during_call.append(await self.state.get_state())
        if self.error is not None:
            raise self.error
        return SUMMARY


def make_callback() -> SimpleNamespace:
    message = Message(
        message_id=1, date=datetime.now(UTC), chat=Chat(id=1, type="private"), text=None
    )
    return SimpleNamespace(message=message, answer=AsyncMock())


def callback_data_of(markup: InlineKeyboardMarkup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


async def prepare(
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    scores: list[int],
    error: Exception | None = None,
) -> tuple[FakeLLM, SessionSummaryService]:
    session_id = await create_session_with_questions(session_factory, questions=make_questions(8))
    for index, score in enumerate(scores, start=1):
        await add_analyzed_answer(
            session_factory, session_id, f"Q-{index:02d}", analysis_with_score(score)
        )
    await state.set_state(InterviewState.NEXT_ACTION)
    await state.update_data(session_id=session_id, question_id="Q-01")
    llm = FakeLLM(state, error)
    return llm, SessionSummaryService(llm, session_factory)


async def test_summary_success(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    llm, service = await prepare(state, session_factory, [7, 8, 6])
    callback = make_callback()

    await session_summary_callback(callback, state, service)

    callback.answer.assert_awaited_once_with()
    assert llm.states_during_call == [InterviewState.GENERATING_SUMMARY.state]
    assert await state.get_state() == InterviewState.SUMMARY_RESULT.state
    assert sent.await_args_list[0].args[0] == GENERATING_SUMMARY_TEXT
    text = sent.await_args.args[0]
    assert text.startswith("🎯 Итоги подготовки\n\nБизнес-аналитик")
    assert "Отвечено: 3 из 8" in text
    assert "Средняя оценка: 7.0/10" in text
    assert "💪 Сильные стороны\n• Структурирует требования" in text
    assert "⚠️ Зоны для улучшения" in text
    assert "⭐ STAR" in text and "Result часто отсутствует" in text
    assert "💡 Рекомендации" in text
    assert "1. SQL JOIN\n2. BPMN" in text
    assert "LLM-позиция" not in text and "99" not in text
    assert callback_data_of(sent.await_args.kwargs["reply_markup"]) == [BACK, MAIN]


async def test_no_answers_does_not_call_openai(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    llm, service = await prepare(state, session_factory, [])

    await session_summary_callback(make_callback(), state, service)

    assert llm.calls == 0
    assert sent.await_count == 1
    assert sent.await_args.args[0] == SUMMARY_NO_ANSWERS_TEXT
    assert await state.get_state() == InterviewState.NEXT_ACTION.state


async def test_cached_summary_is_shown_without_openai(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    llm, service = await prepare(state, session_factory, [7, 8])
    await session_summary_callback(make_callback(), state, service)
    first_text = sent.await_args.args[0]
    sent.reset_mock()

    await session_summary_callback(make_callback(), state, service)

    assert llm.calls == 1
    assert sent.await_count == 1
    assert sent.await_args.args[0] == first_text
    assert await state.get_state() == InterviewState.SUMMARY_RESULT.state


async def test_openai_error_restores_state(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    error = LLMServiceError("OpenAI request failed: API returned status 500")
    llm, service = await prepare(state, session_factory, [7], error)

    await session_summary_callback(make_callback(), state, service)

    assert llm.states_during_call == [InterviewState.GENERATING_SUMMARY.state]
    assert await state.get_state() == InterviewState.NEXT_ACTION.state
    assert sent.await_args.args[0] == SUMMARY_LLM_ERROR_TEXT
    assert "500" not in sent.await_args.args[0]
    assert SUMMARY_CALLBACK in callback_data_of(sent.await_args.kwargs["reply_markup"])


async def test_unexpected_error_restores_state(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    llm, service = await prepare(state, session_factory, [7], RuntimeError("bug"))

    with pytest.raises(RuntimeError):
        await session_summary_callback(make_callback(), state, service)

    assert await state.get_state() == InterviewState.NEXT_ACTION.state


async def test_press_while_generating_is_ignored(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    llm, service = await prepare(state, session_factory, [7])
    await state.set_state(InterviewState.GENERATING_SUMMARY)
    callback = make_callback()

    await session_summary_callback(callback, state, service)

    callback.answer.assert_awaited_once_with(SUMMARY_IN_PROGRESS_TEXT)
    assert llm.calls == 0
    sent.assert_not_awaited()


async def test_messages_during_and_after_summary(sent: AsyncMock) -> None:
    message = make_callback().message

    await generating_summary_message(message)
    assert sent.await_args.args[0] == SUMMARY_IN_PROGRESS_TEXT

    await summary_result_message(message)
    assert sent.await_args.args[0] == SUMMARY_RESULT_HINT_TEXT


def test_summary_button_in_questions_list() -> None:
    data = callback_data_of(questions_keyboard(make_questions(3)))

    assert data == ["question:Q-01", "question:Q-02", "question:Q-03", SUMMARY_CALLBACK, MAIN]
    assert SUMMARY_CALLBACK == "menu:summary"
