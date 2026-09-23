import logging

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.exceptions import DatabaseError, EntityNotFoundError
from app.database.models import Answer, InterviewSession, InterviewSessionStatus
from app.database.repositories import InterviewSessionRepository
from app.schemas.session_summary import InterviewSummary
from app.services.answer_service import AnswerService
from app.services.exceptions import LLMServiceError, NoAnswersError
from app.services.session_summary_service import SessionSummaryService
from answer_helpers import (
    ANSWER_ANALYSIS,
    ANSWER_TEXT,
    SUMMARY,
    add_analyzed_answer,
    analysis_with_score,
    create_session_with_questions,
    make_questions,
)
from openai_mocks import error_response, make_openai_service, output_text_response


def llm_returning(summary: InterviewSummary = SUMMARY):
    return make_openai_service(lambda request: output_text_response(summary.model_dump_json()))


async def session_with_answers(
    session_factory: async_sessionmaker[AsyncSession], scores: list[int], total: int = 8
) -> int:
    session_id = await create_session_with_questions(
        session_factory, questions=make_questions(total)
    )
    for index, score in enumerate(scores, start=1):
        await add_analyzed_answer(
            session_factory, session_id, f"Q-{index:02d}", analysis_with_score(score)
        )
    return session_id


async def load_session(
    session_factory: async_sessionmaker[AsyncSession], session_id: int
) -> InterviewSession:
    async with session_factory() as session:
        return await session.get(InterviewSession, session_id)


async def answer_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(Answer))


async def test_counts_only_answered_questions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await session_with_answers(session_factory, [7, 8, 6, 9, 7, 8])
    llm, transport = llm_returning()

    summary = await SessionSummaryService(llm, session_factory).create_summary(session_id)

    assert (summary.answered_questions, summary.total_questions) == (6, 8)
    assert len(transport.requests) == 1
    content = transport.bodies()[0]["input"][1]["content"]
    assert "answered_questions: 6\ntotal_questions: 8" in content
    assert "[Q-06]" in content and "[Q-07]" not in content


async def test_average_is_calculated_in_python(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await session_with_answers(session_factory, [7, 8, 6, 9])
    llm, transport = llm_returning()

    summary = await SessionSummaryService(llm, session_factory).create_summary(session_id)

    assert summary.average_score == 7.5
    assert "average_score: 7.5" in transport.bodies()[0]["input"][1]["content"]
    assert summary.position == "Бизнес-аналитик"
    assert summary.star_statistics.answers == 2
    assert summary.strong_sides == SUMMARY.strong_sides
    assert summary.priority_topics == SUMMARY.priority_topics


async def test_summary_is_saved(session_factory: async_sessionmaker[AsyncSession]) -> None:
    session_id = await session_with_answers(session_factory, [7, 8, 6])
    llm, _ = llm_returning()

    summary = await SessionSummaryService(llm, session_factory).create_summary(session_id)

    interview_session = await load_session(session_factory, session_id)
    assert InterviewSummary.model_validate_json(interview_session.summary_json) == summary
    assert interview_session.status == InterviewSessionStatus.SUMMARY_RESULT


async def test_no_answers_does_not_call_openai(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await session_with_answers(session_factory, [])
    llm, transport = llm_returning()
    service = SessionSummaryService(llm, session_factory)

    with pytest.raises(NoAnswersError):
        await service.create_summary(session_id)
    with pytest.raises(NoAnswersError):
        await service.get_saved_summary(session_id)

    assert transport.requests == []
    assert (await load_session(session_factory, session_id)).summary_json is None


async def test_answer_without_analysis_is_not_counted(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await session_with_answers(session_factory, [])
    async with session_factory() as session:
        session.add(
            Answer(session_id=session_id, question="Вопрос 1", user_answer=ANSWER_TEXT)
        )
        await session.commit()
    llm, transport = llm_returning()

    with pytest.raises(NoAnswersError):
        await SessionSummaryService(llm, session_factory).create_summary(session_id)
    assert transport.requests == []


async def test_saved_summary_is_reused_without_openai(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await session_with_answers(session_factory, [7, 8])
    llm, transport = llm_returning()
    service = SessionSummaryService(llm, session_factory)

    assert await service.get_saved_summary(session_id) is None
    first = await service.create_summary(session_id)

    assert await service.get_saved_summary(session_id) == first
    assert await service.create_summary(session_id) == first
    assert len(transport.requests) == 1


async def test_new_answer_invalidates_saved_summary(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await session_with_answers(session_factory, [7, 8])
    llm, transport = llm_returning()
    service = SessionSummaryService(llm, session_factory)
    await service.create_summary(session_id)
    answer_llm, _ = make_openai_service(
        lambda request: output_text_response(analysis_with_score(9).model_dump_json())
    )

    await AnswerService(answer_llm, session_factory).analyze_for_session(
        session_id, "Q-03", ANSWER_TEXT
    )

    assert (await load_session(session_factory, session_id)).summary_json is None
    assert await service.get_saved_summary(session_id) is None
    summary = await service.create_summary(session_id)
    assert (summary.answered_questions, summary.average_score) == (3, 8.0)
    assert len(transport.requests) == 2


async def test_stale_saved_summary_is_not_reused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await session_with_answers(session_factory, [7, 8])
    stale = SUMMARY.model_copy(update={"answered_questions": 1, "average_score": 7.0})
    async with session_factory() as session:
        await InterviewSessionRepository(session).save_summary(session_id, stale.model_dump_json())
        await session.commit()

    service = SessionSummaryService(llm_returning()[0], session_factory)

    assert await service.get_saved_summary(session_id) is None


async def test_retried_answer_uses_latest_analysis(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await session_with_answers(session_factory, [4])
    await add_analyzed_answer(session_factory, session_id, "Q-01", analysis_with_score(9))
    llm, _ = llm_returning()

    summary = await SessionSummaryService(llm, session_factory).create_summary(session_id)

    assert (summary.answered_questions, summary.average_score) == (1, 9.0)


async def test_openai_error_keeps_answers(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await session_with_answers(session_factory, [7, 8, 6])
    llm, _ = make_openai_service(error_response(500))

    with pytest.raises(LLMServiceError):
        await SessionSummaryService(llm, session_factory).create_summary(session_id)

    assert await answer_count(session_factory) == 3
    interview_session = await load_session(session_factory, session_id)
    assert interview_session.summary_json is None
    assert interview_session.status == InterviewSessionStatus.QUESTIONS


async def test_save_error_rolls_back(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = await session_with_answers(session_factory, [7, 8, 6])
    llm, _ = llm_returning()

    async def broken_update_status(self, session_id, status):
        raise OperationalError("UPDATE interview_sessions", {}, Exception("disk I/O error"))

    monkeypatch.setattr(InterviewSessionRepository, "update_status", broken_update_status)

    with pytest.raises(DatabaseError):
        await SessionSummaryService(llm, session_factory).create_summary(session_id)

    interview_session = await load_session(session_factory, session_id)
    assert interview_session.summary_json is None
    assert await answer_count(session_factory) == 3


async def test_unknown_session(session_factory: async_sessionmaker[AsyncSession]) -> None:
    llm, transport = llm_returning()

    with pytest.raises(EntityNotFoundError):
        await SessionSummaryService(llm, session_factory).create_summary(999)
    assert transport.requests == []


async def test_prompt_contains_only_needed_data(
    session_factory: async_sessionmaker[AsyncSession], caplog: pytest.LogCaptureFixture
) -> None:
    session_id = await session_with_answers(session_factory, [7])
    llm, transport = llm_returning()

    with caplog.at_level(logging.INFO, logger="app"):
        await SessionSummaryService(llm, session_factory).create_summary(session_id)

    content = transport.bodies()[0]["input"][1]["content"]
    for tag in (
        "vacancy_analysis",
        "session_statistics",
        "interview_questions",
        "candidate_answers",
        "answer_analyses",
    ):
        assert f"<{tag}>" in content and f"</{tag}>" in content
    assert ANSWER_TEXT in content
    assert ANSWER_ANALYSIS.weaknesses[0] in content
    assert ANSWER_ANALYSIS.improved_answer not in content
    assert "telegram" not in content.lower()
    assert "session_id" not in content and "created_at" not in content
    app_log = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("app."))
    assert "Session summary saved" in app_log
    assert ANSWER_TEXT not in app_log
    assert SUMMARY.overall_summary not in app_log
