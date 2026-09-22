import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.exceptions import DatabaseError
from app.database.models import Vacancy
from app.database.repositories.vacancy_repository import VacancyRepository
from app.schemas.vacancy import VacancyAnalysis
from app.services.openai_service import OpenAIService

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

    async def analyze(self, vacancy_text: str) -> VacancyAnalysis:
        return await self.llm.analyze_vacancy(vacancy_text)
