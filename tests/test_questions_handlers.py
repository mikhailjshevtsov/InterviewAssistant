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
from app.bot.handlers.questions import (
    generate_questions_callback,
    question_selected_callback,
)
from app.bot.handlers.vacancy import vacancy_received
from app.bot.states import InterviewState
from app.bot.texts import (
    QUESTION_NOT_FOUND_TEXT,
    QUESTIONS_IN_PROGRESS_TEXT,
    QUESTIONS_LLM_ERROR_TEXT,
    QUESTIONS_UNAVAILABLE_TEXT,
)
from app.schemas.question import InterviewQuestion, QuestionSet
from app.schemas.vacancy import VacancyAnalysis
from app.services.answer_service import AnswerService
from app.services.exceptions import LLMServiceError
from app.services.interview_session_service import InterviewSessionService
from app.services.knowledge_service import KnowledgeService
from app.services.question_service import QuestionService
from app.services.user_service import UserService
from app.services.vacancy_service import VacancyService

VACANCY_TEXT = "Ищем бизнес-аналитика: SQL, BPMN, REST API, сбор требований. " * 3
ANALYSIS = VacancyAnalysis(position="Бизнес-аналитик", company=None, hard_skills=["SQL"])
QUESTION_SET = QuestionSet(
    questions=[
        InterviewQuestion(
            id=f"Q-{index:02d}",
            question=f"Вопрос номер {index} о работе с требованиями и SQL",
            category="behavioral" if index % 2 else "technical",
            difficulty="medium",
            star_required=bool(index % 2),
        )
        for index in range(1, 9)
    ]
)


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    return answer


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1)
    )


class FakeLLM:
    def __init__(self, state: FSMContext, error: Exception | None = None):
        self.state = state
        self.error = error
        self.calls = 0
        self.states_during_call: list[str | None] = []

    async def analyze_vacancy(self, vacancy_text: str) -> VacancyAnalysis:
        return ANALYSIS

    async def generate_questions(self, vacancy_analysis, knowledge_items) -> QuestionSet:
        self.calls += 1
        self.states_during_call.append(await self.state.get_state())
        if self.error is not None:
            raise self.error
        return QUESTION_SET


def make_message(text: str | None = None) -> Message:
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=1, type="private"),
        text=text,
    )


def make_callback() -> SimpleNamespace:
    return SimpleNamespace(message=make_message(), answer=AsyncMock())


def callback_data_of(markup: InlineKeyboardMarkup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


async def analyzed_vacancy(
    state: FSMContext, llm: FakeLLM, session_factory: async_sessionmaker[AsyncSession]
) -> QuestionService:
    """Runs the real Stage 4 vacancy flow and returns a QuestionService for the session."""
    await state.set_state(InterviewState.WAITING_VACANCY)
    message = SimpleNamespace(
        text=VACANCY_TEXT,
        from_user=SimpleNamespace(id=100500, username=None, full_name=None),
        answer=AsyncMock(),
    )
    await vacancy_received(
        message,
        state,
        user_service=UserService(session_factory),
        vacancy_service=VacancyService(session_factory, llm=llm),
        interview_session_service=InterviewSessionService(session_factory),
    )
    assert await state.get_state() == InterviewState.VACANCY_RESULT.state
    markup = message.answer.await_args.kwargs["reply_markup"]
    assert MenuCallback(action=MenuAction.GENERATE_QUESTIONS).pack() in callback_data_of(markup)
    return QuestionService(llm, KnowledgeService(), session_factory)


async def test_generate_questions_flow(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    llm = FakeLLM(state)
    service = await analyzed_vacancy(state, llm, session_factory)
    callback = make_callback()

    await generate_questions_callback(callback, state, service)

    assert llm.states_during_call == [InterviewState.GENERATING_QUESTIONS.state]
    assert await state.get_state() == InterviewState.QUESTIONS.state
    callback.answer.assert_awaited_once_with()
    text = sent.await_args.args[0]
    assert text.startswith("📝 Вопросы для подготовки")
    assert "1. Вопрос номер 1" in text and "8. Вопрос номер 8" in text
    markup = sent.await_args.kwargs["reply_markup"]
    data = callback_data_of(markup)
    assert data[:8] == [f"question:Q-{index:02d}" for index in range(1, 9)]
    assert all(len(item.encode()) <= 64 for item in data)
    buttons = [button.text for row in markup.inline_keyboard for button in row]
    assert buttons[0].startswith("1. Вопрос номер 1")
    assert all(len(text) <= 48 for text in buttons)


async def test_repeated_press_shows_saved_questions_without_llm_call(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    llm = FakeLLM(state)
    service = await analyzed_vacancy(state, llm, session_factory)

    await generate_questions_callback(make_callback(), state, service)
    first_text = sent.await_args.args[0]
    sent.reset_mock()
    await generate_questions_callback(make_callback(), state, service)

    assert llm.calls == 1
    assert sent.await_count == 1
    assert sent.await_args.args[0] == first_text
    assert await state.get_state() == InterviewState.QUESTIONS.state


async def test_press_while_generating_is_ignored(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    llm = FakeLLM(state)
    service = await analyzed_vacancy(state, llm, session_factory)
    await state.set_state(InterviewState.GENERATING_QUESTIONS)
    callback = make_callback()

    await generate_questions_callback(callback, state, service)

    callback.answer.assert_awaited_once_with(QUESTIONS_IN_PROGRESS_TEXT)
    assert llm.calls == 0
    sent.assert_not_awaited()


async def test_llm_error_does_not_leave_generating_state(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    llm = FakeLLM(state, error=LLMServiceError("OpenAI request failed: timeout"))
    service = await analyzed_vacancy(state, llm, session_factory)

    await generate_questions_callback(make_callback(), state, service)

    assert await state.get_state() == InterviewState.VACANCY_RESULT.state
    assert sent.await_args.args[0] == QUESTIONS_LLM_ERROR_TEXT
    retry = sent.await_args.kwargs["reply_markup"]
    assert MenuCallback(action=MenuAction.GENERATE_QUESTIONS).pack() in callback_data_of(retry)
    assert await service.list_questions((await state.get_data())["session_id"]) == []


async def test_unexpected_error_does_not_leave_generating_state(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    llm = FakeLLM(state, error=RuntimeError("bug"))
    service = await analyzed_vacancy(state, llm, session_factory)

    with pytest.raises(RuntimeError):
        await generate_questions_callback(make_callback(), state, service)

    assert await state.get_state() == InterviewState.VACANCY_RESULT.state


async def test_generate_without_session_shows_alert(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    llm = FakeLLM(state)
    callback = make_callback()

    await generate_questions_callback(
        callback, state, QuestionService(llm, KnowledgeService(), session_factory)
    )

    callback.answer.assert_awaited_once_with(QUESTIONS_UNAVAILABLE_TEXT, show_alert=True)
    assert llm.calls == 0


async def test_select_question_waits_for_answer(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    llm = FakeLLM(state)
    service = await analyzed_vacancy(state, llm, session_factory)
    await generate_questions_callback(make_callback(), state, service)
    callback = make_callback()

    await question_selected_callback(
        callback,
        QuestionCallback(question_id="Q-03"),
        state,
        service,
        AnswerService(llm, session_factory),
    )

    assert await state.get_state() == InterviewState.WAITING_ANSWER.state
    assert (await state.get_data())["question_id"] == "Q-03"
    text = sent.await_args.args[0]
    assert "Вопрос номер 3" in text
    assert "STAR" in text
    assert llm.calls == 1


async def test_select_unknown_question_shows_alert(
    state: FSMContext, sent: AsyncMock, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    llm = FakeLLM(state)
    service = await analyzed_vacancy(state, llm, session_factory)
    await generate_questions_callback(make_callback(), state, service)
    sent.reset_mock()
    callback = make_callback()

    await question_selected_callback(
        callback,
        QuestionCallback(question_id="Q-99"),
        state,
        service,
        AnswerService(llm, session_factory),
    )

    callback.answer.assert_awaited_once_with(QUESTION_NOT_FOUND_TEXT, show_alert=True)
    assert await state.get_state() == InterviewState.QUESTIONS.state
    sent.assert_not_awaited()


def test_question_callback_is_short_and_typed() -> None:
    packed = QuestionCallback(question_id="Q-01").pack()

    assert packed == "question:Q-01"
    assert QuestionCallback.unpack(packed).question_id == "Q-01"
    assert MenuCallback(action=MenuAction.GENERATE_QUESTIONS).pack() == "menu:generate_questions"
