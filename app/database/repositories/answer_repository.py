from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.exceptions import EntityNotFoundError
from app.database.models import Answer


class AnswerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        session_id: int,
        question: str,
        user_answer: str,
        session_question_id: int | None = None,
    ) -> Answer:
        answer = Answer(
            session_id=session_id,
            session_question_id=session_question_id,
            question=question,
            user_answer=user_answer,
        )
        self.session.add(answer)
        await self.session.flush()
        return answer

    async def get_by_id(self, answer_id: int) -> Answer | None:
        return await self.session.get(Answer, answer_id)

    async def get_latest_analyzed(self, session_question_id: int) -> Answer | None:
        result = await self.session.execute(
            select(Answer)
            .where(
                Answer.session_question_id == session_question_id,
                Answer.ai_analysis.is_not(None),
            )
            .order_by(Answer.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_analyzed_by_session(self, session_id: int) -> list[Answer]:
        result = await self.session.execute(
            select(Answer)
            .where(
                Answer.session_id == session_id,
                Answer.session_question_id.is_not(None),
                Answer.ai_analysis.is_not(None),
            )
            .order_by(Answer.id)
        )
        return list(result.scalars())

    async def save_analysis(self, answer_id: int, ai_analysis: str, score: int) -> Answer:
        answer = await self.get_by_id(answer_id)
        if answer is None:
            raise EntityNotFoundError(f"Answer {answer_id} not found")
        answer.ai_analysis = ai_analysis
        answer.score = score
        await self.session.flush()
        return answer
