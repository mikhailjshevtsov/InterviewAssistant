import pytest

from app.config import settings
from app.schemas.answer import AnswerAnalysis
from app.schemas.question import InterviewQuestion, QuestionCategory, QuestionSet
from app.schemas.vacancy import VacancyAnalysis
from app.services.answer_service import AnswerService
from app.services.knowledge_service import KnowledgeService
from app.services.openai_service import OpenAIService
from app.services.question_service import QuestionService, collect_keywords

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not settings.openai_api_key, reason="OPENAI_API_KEY is not set"),
]

ANALYST_VACANCY = VacancyAnalysis(
    position="Бизнес-аналитик",
    company=None,
    hard_skills=["BPMN", "SQL"],
    interview_topics=["оптимизация бизнес-процессов", "требования"],
)
PROCESS_QUESTION = InterviewQuestion(
    id="Q-01",
    question="Расскажите о случае, когда вам пришлось улучшить бизнес-процесс.",
    category="behavioral",
    difficulty="medium",
    star_required=True,
)
WEAK_ANSWER = (
    "На прошлой работе процесс оформления договоров был долгим. Я поговорил с коллегами, "
    "нарисовал схему процесса и предложил убрать лишние шаги. Стало лучше."
)
EXAMPLE_FACTS = ("12 рабочих", "8 сотрудник", "4 рабочих дн", "закупок", "потерянных заявок")

MANAGER_VACANCY = VacancyAnalysis(
    position="Project Manager",
    company=None,
    hard_skills=["Jira", "Scrum", "управление рисками"],
    soft_skills=["коммуникация со стейкхолдерами"],
    responsibilities=["планирование сроков и бюджета проекта", "управление командой разработки"],
    interview_topics=["планирование", "риски", "стейкхолдеры", "Scrum"],
)
MANAGER_TERMS = ("проект", "срок", "риск", "бюджет", "команд", "стейкхолдер", "scrum", "jira", "план")


async def test_real_answer_analysis_does_not_copy_star_examples() -> None:
    knowledge_service = KnowledgeService()
    examples = await knowledge_service.find_star_examples(
        ANALYST_VACANCY.position,
        [PROCESS_QUESTION.category],
        [PROCESS_QUESTION.question, *ANALYST_VACANCY.hard_skills],
    )
    assert "STAR-001" in [example.id for example in examples]

    llm = OpenAIService.from_settings()
    try:
        result = await AnswerService(llm, knowledge_service=knowledge_service).analyze(
            PROCESS_QUESTION, WEAK_ANSWER, ANALYST_VACANCY
        )
    finally:
        await llm.close()

    assert isinstance(result, AnswerAnalysis)
    assert result.score <= 7
    produced = " ".join([result.improved_answer or "", *result.strengths]).lower()
    for fact in EXAMPLE_FACTS:
        assert fact not in produced


async def test_real_new_profession_knowledge_to_questions_flow() -> None:
    knowledge_service = KnowledgeService()
    knowledge_items = await knowledge_service.find_relevant(
        MANAGER_VACANCY.position, list(QuestionCategory), collect_keywords(MANAGER_VACANCY)
    )
    professions = [item.profession for item in knowledge_items]
    assert professions[:12] == ["manager"] * 12

    llm = OpenAIService.from_settings()
    try:
        result = await QuestionService(llm, knowledge_service).generate(
            MANAGER_VACANCY, knowledge_items
        )
    finally:
        await llm.close()

    assert isinstance(result, QuestionSet)
    assert 1 <= len(result.questions) <= 10
    relevant = [
        question
        for question in result.questions
        if any(term in question.question.lower() for term in MANAGER_TERMS)
    ]
    assert len(relevant) >= len(result.questions) // 2
    assert any(question.star_required for question in result.questions)
