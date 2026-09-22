from typing import Any
from app.services.openai_service import OpenAIService

class QuestionService:
    def __init__(self, llm: OpenAIService):
        self.llm = llm

    async def generate(
        self,
        vacancy_analysis: dict[str, Any],
        knowledge_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return await self.llm.generate_questions(
            vacancy_analysis, knowledge_items
        )
