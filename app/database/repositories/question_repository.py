from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import SessionQuestion


class SessionQuestionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        session_id: int,
        question_id: str,
        question: str,
        category: str,
        difficulty: str,
        star_required: bool,
    ) -> SessionQuestion:
        entity = SessionQuestion(
            session_id=session_id,
            question_id=question_id,
            question=question,
            category=category,
            difficulty=difficulty,
            star_required=star_required,
        )
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def list_by_session(self, session_id: int) -> list[SessionQuestion]:
        result = await self.session.execute(
            select(SessionQuestion)
            .where(SessionQuestion.session_id == session_id)
            .order_by(SessionQuestion.id)
        )
        return list(result.scalars())

    async def get_by_question_id(
        self, session_id: int, question_id: str
    ) -> SessionQuestion | None:
        result = await self.session.execute(
            select(SessionQuestion).where(
                SessionQuestion.session_id == session_id,
                SessionQuestion.question_id == question_id,
            )
        )
        return result.scalar_one_or_none()
