import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.exceptions import DatabaseError, EntityNotFoundError
from app.database.models import Vacancy
from app.database.repositories.vacancy_repository import VacancyRepository
from app.schemas.vacancy import VacancyAnalysis
from app.services.exceptions import InvalidVacancyTextError
from app.services.openai_service import OpenAIService
from app.services.vacancy_validator import validate_vacancy_text

logger = logging.getLogger(__name__)


class VacancyService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm: OpenAIService | None = None,
    ):
        self.session_factory = session_factory
        self.llm = llm or OpenAIService()

    async def create(self, user_id: int, vacancy_text: str) -> Vacancy:
        async with self.session_factory() as session:
            try:
                vacancy = await VacancyRepository(session).create(user_id, vacancy_text)
                await session.commit()
                await session.refresh(vacancy)
            except SQLAlchemyError as exc:
                await session.rollback()
                logger.exception("Failed to create vacancy for user_id=%s", user_id)
                raise DatabaseError("Failed to create vacancy") from exc
        return vacancy

    async def analyze(self, vacancy_id: int) -> VacancyAnalysis:
        vacancy_text = await self._get_vacancy_text(vacancy_id)
        validation = validate_vacancy_text(vacancy_text)
        if validation.error is not None:
            logger.info(
                "Vacancy analysis skipped: invalid text (vacancy_id=%s, reason=%s)",
                vacancy_id,
                validation.error,
            )
            raise InvalidVacancyTextError(validation.error)

        logger.info("Vacancy analysis started (vacancy_id=%s)", vacancy_id)
        analysis = await self.llm.analyze_vacancy(validation.text)
        logger.info("Vacancy analysis completed (vacancy_id=%s)", vacancy_id)

        await self._save_analysis(vacancy_id, analysis)
        return analysis

    async def _get_vacancy_text(self, vacancy_id: int) -> str:
        async with self.session_factory() as session:
            try:
                vacancy = await VacancyRepository(session).get_by_id(vacancy_id)
            except SQLAlchemyError as exc:
                logger.exception("Failed to load vacancy_id=%s", vacancy_id)
                raise DatabaseError("Failed to load vacancy") from exc
        if vacancy is None:
            raise EntityNotFoundError(f"Vacancy {vacancy_id} not found")
        return vacancy.text

    async def _save_analysis(self, vacancy_id: int, analysis: VacancyAnalysis) -> None:
        async with self.session_factory() as session:
            try:
                await VacancyRepository(session).save_analysis(
                    vacancy_id,
                    position=analysis.position,
                    analysis_json=analysis.model_dump_json(),
                )
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                logger.exception("Failed to save analysis for vacancy_id=%s", vacancy_id)
                raise DatabaseError("Failed to save vacancy analysis") from exc
        logger.info("Vacancy analysis saved (vacancy_id=%s)", vacancy_id)
