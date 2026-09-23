import logging
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.exceptions import DatabaseError, EntityNotFoundError
from app.database.models import InterviewSessionStatus, SessionQuestion
from app.database.repositories.answer_repository import AnswerRepository
from app.database.repositories.question_repository import SessionQuestionRepository
from app.database.repositories.session_repository import InterviewSessionRepository
from app.database.repositories.vacancy_repository import VacancyRepository
from app.schemas.answer import AnswerAnalysis
from app.schemas.question import InterviewQuestion
from app.schemas.vacancy import VacancyAnalysis
from app.services.answer_validator import validate_answer_text
from app.services.exceptions import InvalidAnswerTextError, LLMServiceError
from app.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _AnswerContext:
    session_question_id: int
    question: InterviewQuestion
    vacancy_analysis: VacancyAnalysis


class AnswerService:
    def __init__(
        self,
        llm: OpenAIService,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ):
        self.llm = llm
        self.session_factory = session_factory

    async def analyze(
        self,
        question: InterviewQuestion,
        answer: str,
        vacancy_analysis: VacancyAnalysis,
    ) -> AnswerAnalysis:
        validation = validate_answer_text(answer)
        if validation.error is not None:
            raise InvalidAnswerTextError(validation.error)
        analysis = await self.llm.analyze_answer(question, validation.text, vacancy_analysis)
        if not isinstance(analysis, AnswerAnalysis):
            raise LLMServiceError("LLM returned no AnswerAnalysis")
        return analysis

    async def analyze_for_session(
        self, session_id: int, question_id: str, answer: str
    ) -> AnswerAnalysis:
        validation = validate_answer_text(answer)
        if validation.error is not None:
            raise InvalidAnswerTextError(validation.error)

        context = await self._load_context(session_id, question_id)
        logger.info(
            "Answer analysis started (session_id=%s, question_id=%s, answer_length=%s)",
            session_id,
            question_id,
            len(validation.text),
        )
        analysis = await self.analyze(context.question, validation.text, context.vacancy_analysis)
        logger.info(
            "Answer analysis completed (session_id=%s, question_id=%s, score=%s)",
            session_id,
            question_id,
            analysis.score,
        )
        await self._save(session_id, context, validation.text, analysis)
        return analysis

    async def get_saved_analysis(self, session_id: int, question_id: str) -> AnswerAnalysis | None:
        async with self._session() as session:
            try:
                session_question = await self._get_session_question(
                    session, session_id, question_id
                )
                answer = await AnswerRepository(session).get_latest_analyzed(session_question.id)
            except SQLAlchemyError as exc:
                logger.exception("Failed to load saved answer (session_id=%s)", session_id)
                raise DatabaseError("Failed to load saved answer") from exc
        if answer is None or answer.ai_analysis is None:
            return None
        try:
            return AnswerAnalysis.model_validate_json(answer.ai_analysis)
        except ValidationError:
            logger.warning("Saved answer analysis is invalid (answer_id=%s)", answer.id)
            return None

    def _session(self) -> AsyncSession:
        if self.session_factory is None:
            raise RuntimeError("AnswerService was created without a session factory")
        return self.session_factory()

    @staticmethod
    async def _get_session_question(
        session: AsyncSession, session_id: int, question_id: str
    ) -> SessionQuestion:
        session_question = await SessionQuestionRepository(session).get_by_question_id(
            session_id, question_id
        )
        if session_question is None:
            raise EntityNotFoundError(
                f"Question {question_id} not found in session {session_id}"
            )
        return session_question

    async def _load_context(self, session_id: int, question_id: str) -> _AnswerContext:
        async with self._session() as session:
            try:
                session_question = await self._get_session_question(
                    session, session_id, question_id
                )
                interview_session = await InterviewSessionRepository(session).get_by_id(
                    session_id
                )
                vacancy = (
                    await VacancyRepository(session).get_by_id(interview_session.vacancy_id)
                    if interview_session is not None
                    else None
                )
            except SQLAlchemyError as exc:
                logger.exception("Failed to load answer context (session_id=%s)", session_id)
                raise DatabaseError("Failed to load answer context") from exc
        if vacancy is None or vacancy.analysis_json is None:
            raise EntityNotFoundError(f"Vacancy analysis for session {session_id} not found")
        try:
            vacancy_analysis = VacancyAnalysis.model_validate_json(vacancy.analysis_json)
        except ValidationError as exc:
            raise EntityNotFoundError(f"Vacancy {vacancy.id} has invalid analysis") from exc
        question = InterviewQuestion(
            id=session_question.question_id,
            question=session_question.question,
            category=session_question.category,
            difficulty=session_question.difficulty,
            star_required=session_question.star_required,
        )
        return _AnswerContext(session_question.id, question, vacancy_analysis)

    async def _save(
        self,
        session_id: int,
        context: _AnswerContext,
        answer: str,
        analysis: AnswerAnalysis,
    ) -> None:
        async with self._session() as session:
            try:
                repository = AnswerRepository(session)
                entity = await repository.create(
                    session_id=session_id,
                    question=context.question.question,
                    user_answer=answer,
                    session_question_id=context.session_question_id,
                )
                await repository.save_analysis(
                    entity.id, analysis.model_dump_json(), analysis.score
                )
                session_repository = InterviewSessionRepository(session)
                await session_repository.update_status(
                    session_id, InterviewSessionStatus.ANSWER_RESULT
                )
                await session_repository.save_summary(session_id, None)
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                logger.exception("Failed to save answer (session_id=%s)", session_id)
                raise DatabaseError("Failed to save answer") from exc
        logger.info(
            "Answer analysis saved (session_id=%s, question_id=%s, answer_id=%s)",
            session_id,
            context.question.id,
            entity.id,
        )
