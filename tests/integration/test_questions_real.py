import pytest

from app.config import settings
from app.schemas.knowledge import KnowledgeItem
from app.schemas.question import QuestionCategory, QuestionSet
from app.schemas.vacancy import VacancyAnalysis
from app.services.knowledge_service import KnowledgeService
from app.services.openai_service import OpenAIService
from app.services.question_service import QuestionService, collect_keywords

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not settings.openai_api_key, reason="OPENAI_API_KEY is not set"),
]

ANALYSIS = VacancyAnalysis(
    position="Бизнес-аналитик (Middle)",
    company="Ромашка",
    hard_skills=["SQL", "BPMN", "REST API"],
    soft_skills=["коммуникативные навыки"],
    experience=["опыт работы бизнес-аналитиком от 2 лет"],
    responsibilities=[
        "сбор и анализ требований от заказчиков",
        "описание бизнес-процессов в BPMN",
        "подготовка технических заданий",
    ],
    interview_topics=["SQL", "BPMN", "REST API", "управление требованиями"],
)
RELEVANT_TERMS = ("sql", "bpmn", "rest", "api", "требован", "процесс", "тз", "техническ", "заказчик")


def assert_valid_and_relevant(result: QuestionSet) -> None:
    assert isinstance(result, QuestionSet)
    assert 1 <= len(result.questions) <= 10
    ids = [question.id for question in result.questions]
    assert len(set(ids)) == len(ids)
    relevant = [
        question
        for question in result.questions
        if any(term in question.question.lower() for term in RELEVANT_TERMS)
    ]
    assert len(relevant) >= len(result.questions) // 2


async def test_real_generate_questions() -> None:
    knowledge_items = [
        KnowledgeItem(
            id="1",
            profession="analyst",
            category="technical",
            question="Чем REST отличается от SOAP?",
            difficulty="easy",
            keywords=["REST", "SOAP", "API"],
        ),
        KnowledgeItem(
            id="2",
            profession="analyst",
            category="behavioral",
            question="Расскажите о сложном проекте.",
            difficulty="medium",
            star_required=True,
            keywords=["project", "STAR"],
        ),
    ]
    service = OpenAIService.from_settings()
    try:
        result = await service.generate_questions(ANALYSIS, knowledge_items)
    finally:
        await service.close()

    assert_valid_and_relevant(result)


async def test_real_knowledge_to_questions_flow() -> None:
    knowledge_service = KnowledgeService()
    knowledge_items = await knowledge_service.find_relevant(
        ANALYSIS.position, list(QuestionCategory), collect_keywords(ANALYSIS)
    )
    assert knowledge_items, "project questions.csv should match a business analyst vacancy"

    llm = OpenAIService.from_settings()
    try:
        result = await QuestionService(llm, knowledge_service).generate(ANALYSIS, knowledge_items)
    finally:
        await llm.close()

    assert_valid_and_relevant(result)
    assert any(question.star_required for question in result.questions)
