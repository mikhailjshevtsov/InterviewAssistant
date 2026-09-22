from typing import Any

class OpenAIService:
    async def analyze_vacancy(self, vacancy_text: str) -> dict[str, Any]:
        raise NotImplementedError

    async def generate_questions(
        self,
        vacancy_analysis: dict[str, Any],
        knowledge_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def analyze_answer(
        self,
        question: str,
        answer: str,
        vacancy_analysis: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError
