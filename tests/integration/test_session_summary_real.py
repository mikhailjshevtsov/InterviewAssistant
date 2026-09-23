import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database.models import Answer, InterviewSession, SessionQuestion, User, Vacancy
from app.schemas.session_summary import InterviewSummary
from app.services.answer_service import AnswerService
from app.services.openai_service import OpenAIService
from app.services.session_summary_service import SessionSummaryService
from answer_helpers import create_session_with_questions, make_questions

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not settings.openai_api_key, reason="OPENAI_API_KEY is not set"),
]

ANSWERS = {
    "Q-01": (
        "На проекте CRM продажи и юристы требовали противоположного. Моей задачей было "
        "согласовать требования до релиза. Я провёл интервью, описал процессы в BPMN и "
        "предложил показывать юридические поля только на этапе договора. Релиз вышел в срок."
    ),
    "Q-02": (
        "Для отчёта по заказам я использую INNER JOIN между заказами и клиентами, а LEFT JOIN — "
        "когда нужно увидеть клиентов без заказов."
    ),
    "Q-03": "Команда сделала интеграцию с платёжным сервисом, всё прошло хорошо.",
}


async def test_real_session_summary_is_saved_with_links(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session_with_questions(session_factory, questions=make_questions(8))
    llm = OpenAIService.from_settings()
    try:
        answer_service = AnswerService(llm, session_factory)
        scores = []
        for question_id, text in ANSWERS.items():
            analysis = await answer_service.analyze_for_session(session_id, question_id, text)
            scores.append(analysis.score)
        summary_service = SessionSummaryService(llm, session_factory)
        summary = await summary_service.create_summary(session_id)
        cached = await summary_service.get_saved_summary(session_id)
    finally:
        await llm.close()

    assert isinstance(summary, InterviewSummary)
    assert (summary.answered_questions, summary.total_questions) == (3, 8)
    assert summary.average_score == round(sum(scores) / len(scores), 1)
    assert summary.overall_summary
    assert summary.recommendations or summary.weak_sides
    assert cached == summary

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Answer, SessionQuestion, InterviewSession, Vacancy, User)
                .join(SessionQuestion, Answer.session_question_id == SessionQuestion.id)
                .join(InterviewSession, SessionQuestion.session_id == InterviewSession.id)
                .join(Vacancy, InterviewSession.vacancy_id == Vacancy.id)
                .join(User, InterviewSession.user_id == User.id)
                .where(InterviewSession.id == session_id)
            )
        ).all()
    assert {row.SessionQuestion.question_id for row in rows} == set(ANSWERS)
    interview_session = rows[0].InterviewSession
    assert InterviewSummary.model_validate_json(interview_session.summary_json) == summary
    assert rows[0].User.telegram_id == 1
