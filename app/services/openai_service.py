from app.schemas.answer import AnswerAnalysis
from app.schemas.question import InterviewQuestion, QuestionSet
from app.schemas.vacancy import VacancyAnalysis


class OpenAIService:
    async def analyze_vacancy(self, vacancy_text: str) -> VacancyAnalysis:
        raise NotImplementedError

    async def generate_questions(
        self,
        vacancy_analysis: VacancyAnalysis,
        knowledge_items: list[InterviewQuestion],
    ) -> QuestionSet:
        raise NotImplementedError

    async def analyze_answer(
        self,
        question: InterviewQuestion,
        answer: str,
        vacancy_analysis: VacancyAnalysis,
    ) -> AnswerAnalysis:
        raise NotImplementedError
