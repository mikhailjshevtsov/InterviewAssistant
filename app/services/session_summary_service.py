import logging
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.exceptions import DatabaseError, EntityNotFoundError
from app.database.models import Answer, InterviewSessionStatus, SessionQuestion
from app.database.repositories.answer_repository import AnswerRepository
from app.database.repositories.question_repository import SessionQuestionRepository
from app.database.repositories.session_repository import InterviewSessionRepository
from app.database.repositories.vacancy_repository import VacancyRepository
from app.schemas.answer import AnswerAnalysis
from app.schemas.question import InterviewQuestion
from app.schemas.session_summary import InterviewSummary
from app.schemas.vacancy import VacancyAnalysis
from app.services.exceptions import LLMServiceError, NoAnswersError
from app.services.openai_service import OpenAIService
from app.services.session_statistics import (
    AnsweredQuestion,
    SessionStatistics,
    calculate_statistics,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _SummaryContext:
    vacancy_analysis: VacancyAnalysis
    answered: list[AnsweredQuestion]
    statistics: SessionStatistics
    cached_summary: InterviewSummary | None


class SessionSummaryService:
    def __init__(
        self,
        llm: OpenAIService,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ):
        self.llm = llm
        self.session_factory = session_factory

    async def get_saved_summary(self, session_id: int) -> InterviewSummary | None:
        """Returns the saved summary if it still matches the session's answers."""
        context = await self._load_context(session_id)
        return context.cached_summary

    async def create_summary(self, session_id: int) -> InterviewSummary:
        """Returns the saved summary or generates, saves and returns a new one."""
        context = await self._load_context(session_id)
        if context.cached_summary is not None:
            logger.info("Session summary reused (session_id=%s)", session_id)
            return context.cached_summary

        statistics = context.statistics
        logger.info(
            "Session summary started (session_id=%s, answered=%s, total=%s)",
            session_id,
            statistics.answered_questions,
            statistics.total_questions,
        )
        generated = await self.llm.summarize_session(
            context.vacancy_analysis, context.answered, statistics
        )
        if not isinstance(generated, InterviewSummary):
            raise LLMServiceError("LLM returned no InterviewSummary")
        try:
            summary = InterviewSummary.model_validate(
                generated.model_dump() | statistics.summary_fields()
            )
        except ValidationError as exc:
            raise LLMServiceError("LLM summary is inconsistent with session statistics") from exc
        await self._save(session_id, summary)
        return summary

    def _session(self) -> AsyncSession:
        if self.session_factory is None:
            raise RuntimeError("SessionSummaryService was created without a session factory")
        return self.session_factory()

    async def _load_context(self, session_id: int) -> _SummaryContext:
        async with self._session() as session:
            try:
                interview_session = await InterviewSessionRepository(session).get_by_id(
                    session_id
                )
                if interview_session is None:
                    raise EntityNotFoundError(f"InterviewSession {session_id} not found")
                vacancy = await VacancyRepository(session).get_by_id(interview_session.vacancy_id)
                questions = await SessionQuestionRepository(session).list_by_session(session_id)
                answers = await AnswerRepository(session).list_analyzed_by_session(session_id)
            except SQLAlchemyError as exc:
                logger.exception("Failed to load session summary data (session_id=%s)", session_id)
                raise DatabaseError("Failed to load session summary data") from exc

        answered = self._answered_questions(questions, answers)
        if not answered:
            raise NoAnswersError(f"Session {session_id} has no analyzed answers")
        if vacancy is None or vacancy.analysis_json is None:
            raise EntityNotFoundError(f"Vacancy analysis for session {session_id} not found")
        try:
            vacancy_analysis = VacancyAnalysis.model_validate_json(vacancy.analysis_json)
        except ValidationError as exc:
            raise EntityNotFoundError(f"Vacancy {vacancy.id} has invalid analysis") from exc

        statistics = calculate_statistics(vacancy_analysis.position, len(questions), answered)
        cached = self._cached_summary(session_id, interview_session.summary_json, statistics)
        return _SummaryContext(vacancy_analysis, answered, statistics, cached)

    @staticmethod
    def _answered_questions(
        questions: list[SessionQuestion], answers: list[Answer]
    ) -> list[AnsweredQuestion]:
        """Only questions with a saved analysis count; a retried question uses its latest answer."""
        latest = {answer.session_question_id: answer for answer in answers}
        answered: list[AnsweredQuestion] = []
        for row in questions:
            answer = latest.get(row.id)
            if answer is None:
                continue
            try:
                analysis = AnswerAnalysis.model_validate_json(answer.ai_analysis)
            except ValidationError:
                logger.warning("Saved answer analysis is invalid (answer_id=%s)", answer.id)
                continue
            question = InterviewQuestion(
                id=row.question_id,
                question=row.question,
                category=row.category,
                difficulty=row.difficulty,
                star_required=row.star_required,
            )
            answered.append(AnsweredQuestion(question, answer.user_answer, analysis))
        return answered

    @staticmethod
    def _cached_summary(
        session_id: int, summary_json: str | None, statistics: SessionStatistics
    ) -> InterviewSummary | None:
        if summary_json is None:
            return None
        try:
            summary = InterviewSummary.model_validate_json(summary_json)
        except ValidationError:
            logger.warning("Saved session summary is invalid (session_id=%s)", session_id)
            return None
        current = InterviewSummary.model_validate(
            summary.model_dump() | statistics.summary_fields()
        )
        return summary if summary == current else None

    async def _save(self, session_id: int, summary: InterviewSummary) -> None:
        async with self._session() as session:
            try:
                repository = InterviewSessionRepository(session)
                await repository.save_summary(session_id, summary.model_dump_json())
                await repository.update_status(session_id, InterviewSessionStatus.SUMMARY_RESULT)
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                logger.exception("Failed to save session summary (session_id=%s)", session_id)
                raise DatabaseError("Failed to save session summary") from exc
        logger.info(
            "Session summary saved (session_id=%s, answered=%s, average_score=%s)",
            session_id,
            summary.answered_questions,
            summary.average_score,
        )
