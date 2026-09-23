from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.callbacks import MenuAction, MenuCallback, QuestionCallback
from app.bot.handlers.answers import (
    analyzing_answer_message,
    answer_received,
    next_action_message,
    next_question_callback,
    retry_answer_callback,
)
from app.bot.handlers.questions import generate_questions_callback, question_selected_callback
from app.bot.states import InterviewState
from app.bot.texts import (
    ANALYZING_ANSWER_TEXT,
    ANSWER_EMPTY_TEXT,
    ANSWER_IN_PROGRESS_TEXT,
    ANSWER_LLM_ERROR_TEXT,
    ANSWER_TOO_SHORT_TEXT,
    LAST_QUESTION_TEXT,
    NEXT_ACTION_HINT_TEXT,
)
from app.schemas.answer import AnswerAnalysis
from app.services.answer_service import AnswerService
from app.services.exceptions import LLMServiceError
from app.services.knowledge_service import KnowledgeService
from app.services.question_service import QuestionService
from answer_helpers import ANSWER_ANALYSIS, ANSWER_TEXT, create_session_with_questions

NEXT = MenuCallback(action=MenuAction.NEXT_QUESTION).pack()
RETRY = MenuCallback(action=MenuAction.RETRY_ANSWER).pack()
BACK = MenuCallback(action=MenuAction.BACK_QUESTIONS).pack()
MAIN = MenuCallback(action=MenuAction.MAIN_MENU).pack()
SUMMARY = MenuCallback(action=MenuAction.SESSION_SUMMARY).pack()


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

    async def analyze_answer(self, question, answer, vacancy_analysis) -> AnswerAnalysis:
        self.calls += 1
        self.states_during_call.append(await self.state.get_state())
        if self.error is not None:
            raise self.error
        return ANSWER_ANALYSIS

    async def generate_questions(self, vacancy_analysis, knowledge_items):
        raise AssertionError("questions must be loaded from the database")


def make_message(text: str | None = None) -> Message:
    return Message(
        message_id=1, date=datetime.now(UTC), chat=Chat(id=1, type="private"), text=text
    )


def make_callback() -> SimpleNamespace:
    return SimpleNamespace(message=make_message(), answer=AsyncMock())


def callback_data_of(markup: InlineKeyboardMarkup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


class Env:
    def __init__(self, state: FSMContext, llm: FakeLLM, session_factory, session_id: int):
        self.state = state
        self.llm = llm
        self.session_id = session_id
        self.question_service = QuestionService(llm, KnowledgeService(), session_factory)
        self.answer_service = AnswerService(llm, session_factory)

    async def select(self, question_id: str) -> SimpleNamespace:
        callback = make_callback()
        await question_selected_callback(
            callback,
            QuestionCallback(question_id=question_id),
            self.state,
            self.question_service,
            self.answer_service,
        )
        return callback

    async def reply(self, text: str | None) -> None:
        await answer_received(make_message(text), self.state, self.answer_service)


async def make_env(
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    error: Exception | None = None,
) -> Env:
    session_id = await create_session_with_questions(session_factory)
    await state.set_state(InterviewState.QUESTIONS)
    await state.update_data(session_id=session_id, vacancy_id=1, user_id=1)
    return Env(state, FakeLLM(state, error), session_factory, session_id)


async def test_answer_success_flow(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    env = await make_env(state, session_factory)
    await env.select("Q-02")
    assert await state.get_state() == InterviewState.WAITING_ANSWER.state
    sent.reset_mock()

    await env.reply(ANSWER_TEXT)

    assert env.llm.states_during_call == [InterviewState.ANALYZING_ANSWER.state]
    assert await state.get_state() == InterviewState.NEXT_ACTION.state
    assert sent.await_args_list[0].args[0] == ANALYZING_ANSWER_TEXT
    text = sent.await_args.args[0]
    assert "📊 Оценка: 7/10" in text
    assert "⭐ STAR-анализ" in text
    assert "Нет измеримого результата" in text
    assert "[укажите результат в цифрах]" in text
    data = callback_data_of(sent.await_args.kwargs["reply_markup"])
    assert data == [NEXT, RETRY, BACK, SUMMARY, MAIN]
    fsm = await state.get_data()
    assert (fsm["session_id"], fsm["question_id"]) == (env.session_id, "Q-02")
    assert (fsm["user_id"], fsm["vacancy_id"]) == (1, 1)
    assert await env.answer_service.get_saved_analysis(env.session_id, "Q-02") == ANSWER_ANALYSIS


async def test_llm_error_returns_to_waiting_answer(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    env = await make_env(state, session_factory, LLMServiceError("OpenAI request failed: 500"))
    await env.select("Q-02")

    await env.reply(ANSWER_TEXT)

    assert await state.get_state() == InterviewState.WAITING_ANSWER.state
    assert sent.await_args.args[0] == ANSWER_LLM_ERROR_TEXT
    assert "500" not in sent.await_args.args[0]
    assert await env.answer_service.get_saved_analysis(env.session_id, "Q-02") is None


async def test_unexpected_error_does_not_stick_in_analyzing(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    env = await make_env(state, session_factory, RuntimeError("bug"))
    await env.select("Q-02")

    with pytest.raises(RuntimeError):
        await env.reply(ANSWER_TEXT)

    assert await state.get_state() == InterviewState.WAITING_ANSWER.state


@pytest.mark.parametrize(
    ("text", "expected"),
    [(None, ANSWER_EMPTY_TEXT), ("   ", ANSWER_EMPTY_TEXT), ("да", ANSWER_TOO_SHORT_TEXT)],
)
async def test_invalid_answer_does_not_call_openai(
    state: FSMContext,
    sent: AsyncMock,
    session_factory: async_sessionmaker[AsyncSession],
    text: str | None,
    expected: str,
) -> None:
    env = await make_env(state, session_factory)
    await env.select("Q-02")
    sent.reset_mock()

    await env.reply(text)

    assert env.llm.calls == 0
    sent.assert_awaited_once_with(expected)
    assert await state.get_state() == InterviewState.WAITING_ANSWER.state


async def test_messages_while_analyzing_and_after_result(
    state: FSMContext, sent: AsyncMock
) -> None:
    await analyzing_answer_message(make_message("ещё ответ"))
    assert sent.await_args.args[0] == ANSWER_IN_PROGRESS_TEXT

    await next_action_message(make_message("что дальше"))
    assert sent.await_args.args[0] == NEXT_ACTION_HINT_TEXT
    assert NEXT in callback_data_of(sent.await_args.kwargs["reply_markup"])


async def test_next_question_waits_for_answer(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    env = await make_env(state, session_factory)
    await env.select("Q-02")
    await env.reply(ANSWER_TEXT)
    callback = make_callback()

    await next_question_callback(callback, state, env.question_service, env.answer_service)

    callback.answer.assert_awaited_once_with()
    assert await state.get_state() == InterviewState.WAITING_ANSWER.state
    assert (await state.get_data())["question_id"] == "Q-03"
    assert "Как вы описываете процессы в BPMN?" in sent.await_args.args[0]
    assert env.llm.calls == 1


async def test_next_after_last_question_shows_list(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    env = await make_env(state, session_factory)
    await env.select("Q-03")
    await env.reply(ANSWER_TEXT)

    await next_question_callback(make_callback(), state, env.question_service, env.answer_service)

    assert await state.get_state() == InterviewState.QUESTIONS.state
    text = sent.await_args.args[0]
    assert text.startswith(LAST_QUESTION_TEXT)
    data = callback_data_of(sent.await_args.kwargs["reply_markup"])
    assert data[:3] == ["question:Q-01", "question:Q-02", "question:Q-03"]


async def test_back_to_questions_shows_saved_list(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    env = await make_env(state, session_factory)
    await env.select("Q-02")
    await env.reply(ANSWER_TEXT)

    await generate_questions_callback(make_callback(), state, env.question_service)

    assert await state.get_state() == InterviewState.QUESTIONS.state
    assert "question:Q-01" in callback_data_of(sent.await_args.kwargs["reply_markup"])
    assert env.llm.calls == 1


async def test_answered_question_shows_saved_result_without_llm(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    env = await make_env(state, session_factory)
    await env.select("Q-02")
    await env.reply(ANSWER_TEXT)
    sent.reset_mock()

    await env.select("Q-02")

    assert env.llm.calls == 1
    assert await state.get_state() == InterviewState.NEXT_ACTION.state
    text = sent.await_args.args[0]
    assert text.startswith("❓ Вопрос Q-02\n\nРасскажите о сложном согласовании")
    assert "\n\n✅ Вы уже отвечали на этот вопрос.\n\n" in text
    assert "📊 Оценка: 7/10" in text
    assert RETRY in callback_data_of(sent.await_args.kwargs["reply_markup"])


async def test_retry_answer_reanalyzes_after_explicit_action(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    env = await make_env(state, session_factory)
    await env.select("Q-02")
    await env.reply(ANSWER_TEXT)
    callback = make_callback()

    await retry_answer_callback(callback, state, env.question_service)

    callback.answer.assert_awaited_once_with()
    assert await state.get_state() == InterviewState.WAITING_ANSWER.state
    assert "Расскажите о сложном согласовании" in sent.await_args.args[0]
    await env.reply(ANSWER_TEXT + " Сроки сократили на 20%.")
    assert env.llm.calls == 2
    assert await state.get_state() == InterviewState.NEXT_ACTION.state


def test_answer_callbacks_are_short_and_typed() -> None:
    assert (NEXT, RETRY, BACK) == (
        "menu:next_question",
        "menu:retry_answer",
        "menu:back_questions",
    )
    assert all(len(item.encode()) <= 64 for item in (NEXT, RETRY, BACK))
