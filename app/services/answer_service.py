from app.schemas.answer import AnswerAnalysis
from app.schemas.question import InterviewQuestion
from app.schemas.vacancy import VacancyAnalysis
from app.services.openai_service import OpenAIService


class AnswerService:
    def __init__(self, llm: OpenAIService):
        self.llm = llm

    async def analyze(
        self,
        question: InterviewQuestion,
        answer: str,
        vacancy_analysis: VacancyAnalysis,
    ) -> AnswerAnalysis:
        return await self.llm.analyze_answer(question, answer, vacancy_analysis)
