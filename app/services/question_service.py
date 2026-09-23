import logging
import re

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.exceptions import DatabaseError, EntityNotFoundError
from app.database.models import InterviewSessionStatus, SessionQuestion
from app.database.repositories.question_repository import SessionQuestionRepository
from app.database.repositories.session_repository import InterviewSessionRepository
from app.database.repositories.vacancy_repository import VacancyRepository
from app.schemas.knowledge import KnowledgeItem
from app.schemas.question import InterviewQuestion, QuestionCategory, QuestionSet
from app.schemas.vacancy import VacancyAnalysis
from app.services.exceptions import LLMServiceError, QuestionGenerationError
from app.services.knowledge_service import DEFAULT_MAX_ITEMS, KnowledgeService
from app.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)

# Question ids end up in Telegram callback_data, which is limited to 64 bytes
# and uses ":" as a separator.
QUESTION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def collect_keywords(analysis: VacancyAnalysis) -> list[str]:
    return [
        *analysis.hard_skills,
        *analysis.soft_skills,
        *analysis.interview_topics,
        *analysis.responsibilities,
    ]


class QuestionService:
    def __init__(
        self,
        llm: OpenAIService,
        knowledge_service: KnowledgeService | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        max_knowledge_items: int = DEFAULT_MAX_ITEMS,
    ):
        self.llm = llm
        self.knowledge_service = knowledge_service or KnowledgeService()
        self.session_factory = session_factory
        self.max_knowledge_items = max_knowledge_items

    async def generate(
        self,
        vacancy_analysis: VacancyAnalysis,
        knowledge_items: list[KnowledgeItem],
    ) -> QuestionSet:
        if not vacancy_analysis.position and not collect_keywords(vacancy_analysis):
            raise QuestionGenerationError("Vacancy analysis has no data to build questions")
        question_set = await self.llm.generate_questions(
            vacancy_analysis, knowledge_items[: self.max_knowledge_items]
        )
        self._validate(question_set)
        return question_set

    async def generate_for_session(self, session_id: int) -> QuestionSet:
        existing = await self.list_questions(session_id)
        if existing:
            logger.info(
                "Questions already exist, reusing them (session_id=%s, question_count=%s)",
                session_id,
                len(existing),
            )
            return QuestionSet(questions=existing)

        vacancy_id, analysis = await self._load_vacancy_analysis(session_id)
        logger.info(
            "Question generation started (session_id=%s, vacancy_id=%s)", session_id, vacancy_id
        )
        knowledge_items = await self.knowledge_service.find_relevant(
            profession=analysis.position,
            categories=list(QuestionCategory),
            keywords=collect_keywords(analysis),
        )
        logger.info(
            "Knowledge items found: %s (session_id=%s)", len(knowledge_items), session_id
        )
        question_set = await self.generate(analysis, knowledge_items)
        logger.info(
            "Question generation completed (session_id=%s, question_count=%s)",
            session_id,
            len(question_set.questions),
        )
        await self._save(session_id, question_set)
        return question_set

    async def list_questions(self, session_id: int) -> list[InterviewQuestion]:
        async with self._session() as session:
            try:
                rows = await SessionQuestionRepository(session).list_by_session(session_id)
            except SQLAlchemyError as exc:
                logger.exception("Failed to load questions (session_id=%s)", session_id)
                raise DatabaseError("Failed to load questions") from exc
        return [self._to_dto(row) for row in rows]

    async def get_question(self, session_id: int, question_id: str) -> InterviewQuestion | None:
        async with self._session() as session:
            try:
                row = await SessionQuestionRepository(session).get_by_question_id(
                    session_id, question_id
                )
            except SQLAlchemyError as exc:
                logger.exception("Failed to load question (session_id=%s)", session_id)
                raise DatabaseError("Failed to load question") from exc
        return self._to_dto(row) if row is not None else None

    async def get_next_question(
        self, session_id: int, question_id: str
    ) -> InterviewQuestion | None:
        """Returns the question after question_id in session order, or None after the last."""
        questions = await self.list_questions(session_id)
        ids = [question.id for question in questions]
        if question_id not in ids:
            return questions[0] if questions else None
        position = ids.index(question_id) + 1
        return questions[position] if position < len(questions) else None

    def _session(self) -> AsyncSession:
        if self.session_factory is None:
            raise RuntimeError("QuestionService was created without a session factory")
        return self.session_factory()

    async def _load_vacancy_analysis(self, session_id: int) -> tuple[int, VacancyAnalysis]:
        async with self._session() as session:
            try:
                interview_session = await InterviewSessionRepository(session).get_by_id(
                    session_id
                )
                vacancy = (
                    await VacancyRepository(session).get_by_id(interview_session.vacancy_id)
                    if interview_session is not None
                    else None
                )
            except SQLAlchemyError as exc:
                logger.exception("Failed to load vacancy (session_id=%s)", session_id)
                raise DatabaseError("Failed to load vacancy") from exc
        if vacancy is None:
            raise EntityNotFoundError(f"Vacancy for session {session_id} not found")
        if vacancy.analysis_json is None:
            raise QuestionGenerationError(f"Vacancy {vacancy.id} has not been analyzed")
        try:
            return vacancy.id, VacancyAnalysis.model_validate_json(vacancy.analysis_json)
        except ValidationError as exc:
            raise QuestionGenerationError(f"Vacancy {vacancy.id} has invalid analysis") from exc

    async def _save(self, session_id: int, question_set: QuestionSet) -> None:
        async with self._session() as session:
            try:
                repository = SessionQuestionRepository(session)
                for question in question_set.questions:
                    await repository.create(
                        session_id=session_id,
                        question_id=question.id,
                        question=question.question,
                        category=question.category.value,
                        difficulty=question.difficulty.value,
                        star_required=question.star_required,
                    )
                await InterviewSessionRepository(session).update_status(
                    session_id, InterviewSessionStatus.QUESTIONS
                )
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                logger.exception("Failed to save questions (session_id=%s)", session_id)
                raise DatabaseError("Failed to save questions") from exc
        logger.info(
            "Questions saved (session_id=%s, question_count=%s)",
            session_id,
            len(question_set.questions),
        )

    @staticmethod
    def _validate(question_set: QuestionSet) -> None:
        if not isinstance(question_set, QuestionSet):
            raise LLMServiceError("LLM returned no QuestionSet")
        ids = [question.id for question in question_set.questions]
        if len(set(ids)) != len(ids):
            logger.warning("LLM returned duplicate question ids")
            raise LLMServiceError("LLM returned duplicate question ids")
        if not all(QUESTION_ID_RE.fullmatch(question_id) for question_id in ids):
            logger.warning("LLM returned question ids unsuitable for callbacks")
            raise LLMServiceError("LLM returned invalid question ids")

    @staticmethod
    def _to_dto(row: SessionQuestion) -> InterviewQuestion:
        return InterviewQuestion(
            id=row.question_id,
            question=row.question,
            category=row.category,
            difficulty=row.difficulty,
            star_required=row.star_required,
        )
