import json
import logging

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.exceptions import DatabaseError, EntityNotFoundError
from app.database.models import Answer, InterviewSession, InterviewSessionStatus, SessionQuestion
from app.database.repositories import AnswerRepository
from app.knowledge.csv_repository import CsvKnowledgeRepository
from app.schemas.answer import AnswerAnalysis
from app.services.answer_service import AnswerService
from app.services.knowledge_service import KnowledgeService
from app.services.answer_validator import AnswerValidationError
from app.services.exceptions import InvalidAnswerTextError, LLMServiceError
from answer_helpers import (
    ANSWER_ANALYSIS,
    ANSWER_TEXT,
    QUESTIONS,
    VACANCY_ANALYSIS,
    create_session_with_questions,
)
from openai_mocks import error_response, make_openai_service, output_text_response


def llm_returning(analysis: AnswerAnalysis = ANSWER_ANALYSIS):
    return make_openai_service(lambda request: output_text_response(analysis.model_dump_json()))


async def saved_answers(session_factory: async_sessionmaker[AsyncSession]) -> list[Answer]:
    async with session_factory() as session:
        return list((await session.execute(select(Answer).order_by(Answer.id))).scalars())


async def test_analyze_for_session_returns_dto_and_saves_answer(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session_with_questions(session_factory)
    llm, transport = llm_returning()
    service = AnswerService(llm, session_factory)

    result = await service.analyze_for_session(session_id, "Q-02", f"  {ANSWER_TEXT}  ")

    assert isinstance(result, AnswerAnalysis)
    assert result == ANSWER_ANALYSIS
    assert len(transport.requests) == 1
    [answer] = await saved_answers(session_factory)
    async with session_factory() as session:
        session_question = await session.get(SessionQuestion, answer.session_question_id)
        interview_session = await session.get(InterviewSession, session_id)
    assert answer.session_id == session_id
    assert session_question.session_id == session_id
    assert session_question.question_id == "Q-02"
    assert answer.question == QUESTIONS[1].question
    assert answer.user_answer == ANSWER_TEXT
    assert answer.score == 7
    assert AnswerAnalysis.model_validate_json(answer.ai_analysis) == ANSWER_ANALYSIS
    assert interview_session.status == InterviewSessionStatus.ANSWER_RESULT


async def test_openai_receives_saved_vacancy_question_and_answer(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session_with_questions(session_factory)
    llm, transport = llm_returning()

    await AnswerService(llm, session_factory).analyze_for_session(session_id, "Q-02", ANSWER_TEXT)

    [body] = transport.bodies()
    content = body["input"][1]["content"]
    assert body["text"]["format"]["name"] == "AnswerAnalysis"
    assert f"<vacancy_analysis>\nПозиция:\n{VACANCY_ANALYSIS.position}" in content
    assert QUESTIONS[1].question in content
    assert "Ожидается ответ по STAR: да" in content
    assert f"<candidate_answer>\n{ANSWER_TEXT}\n</candidate_answer>" in content


async def test_star_question_receives_star_examples_without_ids(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session_with_questions(session_factory)
    llm, transport = llm_returning()
    service = AnswerService(llm, session_factory, KnowledgeService())

    await service.analyze_for_session(session_id, "Q-02", ANSWER_TEXT)

    [body] = transport.bodies()
    content = body["input"][1]["content"]
    examples = content.split("<star_examples>\n", 1)[1].split("\n</star_examples>", 1)[0]
    assert "Пример 1" in examples and "Пример 2" in examples
    assert "Situation:" in examples and "Result:" in examples
    assert "STAR-" not in content
    assert "Правила для <star_examples>" in body["input"][0]["content"]


@pytest.mark.parametrize(
    ("question_id", "knowledge_service"),
    [("Q-01", KnowledgeService()), ("Q-02", None)],
)
async def test_star_examples_are_sent_only_for_star_questions(
    session_factory: async_sessionmaker[AsyncSession],
    question_id: str,
    knowledge_service: KnowledgeService | None,
) -> None:
    session_id = await create_session_with_questions(session_factory)
    llm, transport = llm_returning()

    await AnswerService(llm, session_factory, knowledge_service).analyze_for_session(
        session_id, question_id, ANSWER_TEXT
    )

    [body] = transport.bodies()
    assert "<star_examples>" not in body["input"][1]["content"]


async def test_missing_star_examples_file_does_not_break_analysis(
    session_factory: async_sessionmaker[AsyncSession], tmp_path
) -> None:
    session_id = await create_session_with_questions(session_factory)
    llm, transport = llm_returning()
    knowledge_service = KnowledgeService(CsvKnowledgeRepository(tmp_path / "questions.csv"))

    result = await AnswerService(llm, session_factory, knowledge_service).analyze_for_session(
        session_id, "Q-02", ANSWER_TEXT
    )

    assert result == ANSWER_ANALYSIS
    [body] = transport.bodies()
    assert "<star_examples>" not in body["input"][1]["content"]


async def test_llm_error_saves_nothing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session_with_questions(session_factory)
    llm, _ = make_openai_service(error_response(500))

    with pytest.raises(LLMServiceError):
        await AnswerService(llm, session_factory).analyze_for_session(
            session_id, "Q-02", ANSWER_TEXT
        )

    assert await saved_answers(session_factory) == []


async def test_save_error_rolls_back(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = await create_session_with_questions(session_factory)
    llm, _ = llm_returning()

    async def broken_save_analysis(self, answer_id: int, ai_analysis: str, score: int):
        raise OperationalError("UPDATE answers", {}, Exception("disk I/O error"))

    monkeypatch.setattr(AnswerRepository, "save_analysis", broken_save_analysis)

    with pytest.raises(DatabaseError):
        await AnswerService(llm, session_factory).analyze_for_session(
            session_id, "Q-02", ANSWER_TEXT
        )

    assert await saved_answers(session_factory) == []
    async with session_factory() as session:
        interview_session = await session.get(InterviewSession, session_id)
    assert interview_session.status == InterviewSessionStatus.QUESTIONS


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("", AnswerValidationError.EMPTY),
        ("   ", AnswerValidationError.EMPTY),
        ("да", AnswerValidationError.TOO_SHORT),
        ("не знаю", AnswerValidationError.TOO_SHORT),
    ],
)
async def test_invalid_answer_does_not_call_openai(
    session_factory: async_sessionmaker[AsyncSession], text: str, error: AnswerValidationError
) -> None:
    session_id = await create_session_with_questions(session_factory)
    llm, transport = llm_returning()
    service = AnswerService(llm, session_factory)

    with pytest.raises(InvalidAnswerTextError) as exc_info:
        await service.analyze_for_session(session_id, "Q-02", text)
    with pytest.raises(InvalidAnswerTextError):
        await service.analyze(QUESTIONS[1], text, VACANCY_ANALYSIS)

    assert exc_info.value.error == error
    assert transport.requests == []
    assert await saved_answers(session_factory) == []


async def test_unknown_question_or_missing_analysis(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session_with_questions(session_factory)
    unanalyzed_id = await create_session_with_questions(session_factory, 2, analyzed=False)
    llm, transport = llm_returning()
    service = AnswerService(llm, session_factory)

    with pytest.raises(EntityNotFoundError):
        await service.analyze_for_session(session_id, "Q-99", ANSWER_TEXT)
    with pytest.raises(EntityNotFoundError):
        await service.analyze_for_session(unanalyzed_id, "Q-01", ANSWER_TEXT)

    assert transport.requests == []


async def test_saved_analysis_is_reused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session_with_questions(session_factory)
    llm, transport = llm_returning()
    service = AnswerService(llm, session_factory)

    assert await service.get_saved_analysis(session_id, "Q-02") is None
    await service.analyze_for_session(session_id, "Q-02", ANSWER_TEXT)

    assert await service.get_saved_analysis(session_id, "Q-02") == ANSWER_ANALYSIS
    assert await service.get_saved_analysis(session_id, "Q-01") is None
    assert len(transport.requests) == 1
    with pytest.raises(EntityNotFoundError):
        await service.get_saved_analysis(session_id, "Q-99")


async def test_retry_saves_new_answer_and_latest_is_shown(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session_with_questions(session_factory)
    better = ANSWER_ANALYSIS.model_copy(update={"score": 9})
    responses = iter([ANSWER_ANALYSIS, better])
    llm, _ = make_openai_service(
        lambda request: output_text_response(next(responses).model_dump_json())
    )
    service = AnswerService(llm, session_factory)

    await service.analyze_for_session(session_id, "Q-02", ANSWER_TEXT)
    await service.analyze_for_session(session_id, "Q-02", ANSWER_TEXT + " Сократили сроки на 20%.")

    assert [answer.score for answer in await saved_answers(session_factory)] == [7, 9]
    assert (await service.get_saved_analysis(session_id, "Q-02")).score == 9


async def test_logs_do_not_contain_answer_text(
    session_factory: async_sessionmaker[AsyncSession], caplog: pytest.LogCaptureFixture
) -> None:
    session_id = await create_session_with_questions(session_factory)
    llm, _ = llm_returning()

    with caplog.at_level(logging.INFO, logger="app"):
        await AnswerService(llm, session_factory).analyze_for_session(
            session_id, "Q-02", ANSWER_TEXT
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any("Answer analysis saved" in message for message in messages)
    assert all(ANSWER_TEXT not in message for message in messages)
    assert all(json.dumps(ANSWER_ANALYSIS.improved_answer) not in m for m in messages)
