from typing import Any
from app.services.openai_service import OpenAIService

class AnswerService:
    def __init__(self, llm: OpenAIService):
        self.llm = llm

    async def analyze(
        self,
        question: str,
        answer: str,
        vacancy_analysis: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.llm.analyze_answer(
            question, answer, vacancy_analysis
        )
