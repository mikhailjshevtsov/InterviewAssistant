from sqlalchemy.ext.asyncio import AsyncSession

from app.database.exceptions import EntityNotFoundError
from app.database.models import Answer


class AnswerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, session_id: int, question: str, user_answer: str) -> Answer:
        answer = Answer(session_id=session_id, question=question, user_answer=user_answer)
        self.session.add(answer)
        await self.session.flush()
        return answer

    async def get_by_id(self, answer_id: int) -> Answer | None:
        return await self.session.get(Answer, answer_id)

    async def save_analysis(self, answer_id: int, ai_analysis: str, score: int) -> Answer:
        answer = await self.get_by_id(answer_id)
        if answer is None:
            raise EntityNotFoundError(f"Answer {answer_id} not found")
        answer.ai_analysis = ai_analysis
        answer.score = score
        await self.session.flush()
        return answer
