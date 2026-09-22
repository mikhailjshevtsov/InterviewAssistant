from typing import Any
from app.services.openai_service import OpenAIService

class VacancyService:
    def __init__(self, llm: OpenAIService):
        self.llm = llm

    async def analyze(self, vacancy_text: str) -> dict[str, Any]:
        return await self.llm.analyze_vacancy(vacancy_text)
