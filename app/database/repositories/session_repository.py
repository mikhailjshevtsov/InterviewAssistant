from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.exceptions import EntityNotFoundError
from app.database.models import InterviewSession, InterviewSessionStatus


class InterviewSessionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: int,
        vacancy_id: int,
        status: InterviewSessionStatus,
    ) -> InterviewSession:
        interview_session = InterviewSession(
            user_id=user_id,
            vacancy_id=vacancy_id,
            status=InterviewSessionStatus(status),
        )
        self.session.add(interview_session)
        await self.session.flush()
        return interview_session

    async def get_by_id(self, session_id: int) -> InterviewSession | None:
        return await self.session.get(InterviewSession, session_id)

    async def get_latest_by_user(self, user_id: int) -> InterviewSession | None:
        result = await self.session.execute(
            select(InterviewSession)
            .where(InterviewSession.user_id == user_id)
            .order_by(InterviewSession.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        session_id: int,
        status: InterviewSessionStatus,
    ) -> InterviewSession:
        interview_session = await self.get_by_id(session_id)
        if interview_session is None:
            raise EntityNotFoundError(f"InterviewSession {session_id} not found")
        interview_session.status = InterviewSessionStatus(status)
        await self.session.flush()
        return interview_session

    async def save_summary(self, session_id: int, summary_json: str | None) -> InterviewSession:
        interview_session = await self.get_by_id(session_id)
        if interview_session is None:
            raise EntityNotFoundError(f"InterviewSession {session_id} not found")
        interview_session.summary_json = summary_json
        await self.session.flush()
        return interview_session
