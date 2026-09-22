from app.schemas.question import InterviewQuestion, QuestionSet
from app.schemas.vacancy import VacancyAnalysis
from app.services.openai_service import OpenAIService


class QuestionService:
    def __init__(self, llm: OpenAIService):
        self.llm = llm

    async def generate(
        self,
        vacancy_analysis: VacancyAnalysis,
        knowledge_items: list[InterviewQuestion],
    ) -> QuestionSet:
        return await self.llm.generate_questions(vacancy_analysis, knowledge_items)
