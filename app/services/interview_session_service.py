import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.exceptions import DatabaseError
from app.database.models import InterviewSession, InterviewSessionStatus
from app.database.repositories.session_repository import InterviewSessionRepository

logger = logging.getLogger(__name__)


class InterviewSessionService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def create(
        self,
        user_id: int,
        vacancy_id: int,
        status: InterviewSessionStatus,
    ) -> InterviewSession:
        async with self.session_factory() as session:
            try:
                interview_session = await InterviewSessionRepository(session).create(
                    user_id, vacancy_id, status
                )
                await session.commit()
                await session.refresh(interview_session)
            except SQLAlchemyError as exc:
                await session.rollback()
                logger.exception(
                    "Failed to create interview session user_id=%s vacancy_id=%s",
                    user_id,
                    vacancy_id,
                )
                raise DatabaseError("Failed to create interview session") from exc
        return interview_session

    async def update_status(
        self,
        session_id: int,
        status: InterviewSessionStatus,
    ) -> InterviewSession:
        async with self.session_factory() as session:
            try:
                interview_session = await InterviewSessionRepository(
                    session
                ).update_status(session_id, status)
                await session.commit()
                await session.refresh(interview_session)
            except SQLAlchemyError as exc:
                await session.rollback()
                logger.exception(
                    "Failed to update interview session status session_id=%s",
                    session_id,
                )
                raise DatabaseError("Failed to update interview session status") from exc
        return interview_session
