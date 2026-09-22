import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.exceptions import DatabaseError
from app.database.models import User
from app.database.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def get_or_create_user(
        self,
        telegram_id: int,
        username: str | None,
        full_name: str | None,
    ) -> User:
        async with self.session_factory() as session:
            try:
                user = await UserRepository(session).get_or_create(
                    telegram_id, username, full_name
                )
                await session.commit()
                await session.refresh(user)
            except SQLAlchemyError as exc:
                await session.rollback()
                logger.exception("Failed to get or create user telegram_id=%s", telegram_id)
                raise DatabaseError("Failed to get or create user") from exc
        return user
