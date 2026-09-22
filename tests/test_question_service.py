import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.exceptions import DatabaseError
from app.database.models import InterviewSession, InterviewSessionStatus, SessionQuestion
from app.database.repositories import VacancyRepository
from app.schemas.knowledge import KnowledgeItem
from app.schemas.question import InterviewQuestion, QuestionSet
from app.schemas.vacancy import VacancyAnalysis
from app.services.exceptions import LLMServiceError, QuestionGenerationError
from app.services.interview_session_service import InterviewSessionService
from app.services.knowledge_service import KnowledgeService
from app.services.question_service import QuestionService
from app.services.user_service import UserService
from app.services.vacancy_service import VacancyService
from openai_mocks import (
    error_response,
    make_openai_service,
    output_text_response,
    refusal_response,
)

VACANCY_TEXT = "Ищем бизнес-аналитика: SQL, BPMN, REST API, сбор требований. " * 3
ANALYSIS = VacancyAnalysis(
    position="Бизнес-аналитик",
    company=None,
    hard_skills=["SQL", "BPMN", "REST API"],
    soft_skills=["коммуникация"],
    responsibilities=["сбор требований"],
    interview_topics=["SQL"],
)
KB_ITEMS = [
    KnowledgeItem(
        id="1",
        profession="analyst",
        category="technical",
        question="Чем REST отличается от SOAP?",
        difficulty="easy",
        keywords=["REST", "SOAP", "API"],
    ),
    KnowledgeItem(
        id="4",
        profession="analyst",
        category="technical",
        question="Какие SQL JOIN вы знаете?",
        difficulty="easy",
        keywords=["SQL", "JOIN"],
    ),
]


def question_payload(count: int = 3, ids: list[str] | None = None) -> dict:
    ids = ids or [f"Q-{index:02d}" for index in range(1, count + 1)]
    return {
        "questions": [
            {
                "id": question_id,
                "question": f"Вопрос {question_id} про SQL",
                "category": "technical",
                "difficulty": "medium",
                "star_required": False,
            }
            for question_id in ids
        ]
    }


def llm_returning(payload: dict):
    return make_openai_service(lambda request: output_text_response(json.dumps(payload)))


def user_content(transport) -> str:
    [body] = transport.bodies()
    return body["input"][1]["content"]


async def test_generate_returns_question_set_with_one_call() -> None:
    llm, transport = llm_returning(question_payload(8))

    result = await QuestionService(llm).generate(ANALYSIS, KB_ITEMS)

    assert isinstance(result, QuestionSet)
    assert [question.id for question in result.questions] == [
        f"Q-{index:02d}" for index in range(1, 9)
    ]
    assert result == QuestionSet.model_validate(question_payload(8))
    assert len(transport.requests) == 1


async def test_llm_receives_vacancy_analysis_and_knowledge_context() -> None:
    llm, transport = llm_returning(question_payload())

    await QuestionService(llm).generate(ANALYSIS, KB_ITEMS)

    content = user_content(transport)
    assert "Бизнес-аналитик" in content
    assert "REST API" in content
    assert "сбор требований" in content
    assert "[KB-1]" in content and "Чем REST отличается от SOAP?" in content
    assert "[KB-4]" in content and "Какие SQL JOIN вы знаете?" in content


async def test_knowledge_items_are_capped() -> None:
    llm, transport = llm_returning(question_payload())
    items = [KB_ITEMS[0].model_copy(update={"id": str(index)}) for index in range(30)]

    await QuestionService(llm, max_knowledge_items=5).generate(ANALYSIS, items)

    content = user_content(transport)
    assert "[KB-4]" in content
    assert "[KB-5]" not in content


async def test_generate_works_without_knowledge_items() -> None:
    llm, transport = llm_returning(question_payload())

    result = await QuestionService(llm).generate(ANALYSIS, [])

    assert len(result.questions) == 3
    assert "Материалы не найдены." in user_content(transport)


async def test_empty_analysis_is_rejected_before_llm_call() -> None:
    llm, transport = llm_returning(question_payload())

    with pytest.raises(QuestionGenerationError):
        await QuestionService(llm).generate(VacancyAnalysis(position=None, company=None), [])

    assert transport.requests == []


async def test_openai_error_becomes_llm_service_error() -> None:
    llm, _ = make_openai_service(lambda request: error_response(500))

    with pytest.raises(LLMServiceError):
        await QuestionService(llm).generate(ANALYSIS, KB_ITEMS)


async def test_refusal_becomes_llm_service_error() -> None:
    llm, _ = make_openai_service(lambda request: refusal_response())

    with pytest.raises(LLMServiceError, match="no QuestionSet"):
        await QuestionService(llm).generate(ANALYSIS, KB_ITEMS)


@pytest.mark.parametrize("count", [0, 11])
async def test_question_count_outside_limits_is_rejected(count: int) -> None:
    llm, _ = llm_returning(question_payload(count) if count else {"questions": []})

    with pytest.raises(LLMServiceError, match="does not match QuestionSet"):
        await QuestionService(llm).generate(ANALYSIS, KB_ITEMS)


async def test_duplicate_question_ids_are_rejected() -> None:
    llm, _ = llm_returning(question_payload(ids=["Q-01", "Q-02", "Q-01"]))

    with pytest.raises(LLMServiceError, match="duplicate"):
        await QuestionService(llm).generate(ANALYSIS, KB_ITEMS)


@pytest.mark.parametrize("bad_id", ["Q:01", "вопрос-1", "Q 01", "Q" * 40])
async def test_callback_unsafe_question_ids_are_rejected(bad_id: str) -> None:
    llm, _ = llm_returning(question_payload(ids=["Q-01", bad_id]))

    with pytest.raises(LLMServiceError, match="invalid question ids"):
        await QuestionService(llm).generate(ANALYSIS, KB_ITEMS)


async def test_empty_question_text_is_rejected() -> None:
    payload = question_payload(2)
    payload["questions"][1]["question"] = "   "
    llm, _ = llm_returning(payload)

    with pytest.raises(LLMServiceError):
        await QuestionService(llm).generate(ANALYSIS, KB_ITEMS)


async def create_session(
    session_factory: async_sessionmaker[AsyncSession], analyzed: bool = True
) -> int:
    user = await UserService(session_factory).get_or_create_user(1, None, None)
    vacancy = await VacancyService(session_factory).create(user.id, VACANCY_TEXT)
    if analyzed:
        async with session_factory() as session:
            await VacancyRepository(session).save_analysis(
                vacancy.id, ANALYSIS.position, ANALYSIS.model_dump_json()
            )
            await session.commit()
    interview_session = await InterviewSessionService(session_factory).create(
        user.id, vacancy.id, InterviewSessionStatus.VACANCY_RESULT
    )
    return interview_session.id


def session_question_service(llm, session_factory) -> QuestionService:
    return QuestionService(llm, KnowledgeService(), session_factory)


async def test_generate_for_session_uses_kb_and_saves_questions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session(session_factory)
    llm, transport = llm_returning(question_payload(8))
    service = session_question_service(llm, session_factory)

    result = await service.generate_for_session(session_id)

    assert len(result.questions) == 8
    content = user_content(transport)
    assert "[KB-4]" in content and "Какие SQL JOIN вы знаете?" in content
    stored = await service.list_questions(session_id)
    assert stored == result.questions
    question = await service.get_question(session_id, "Q-03")
    assert isinstance(question, InterviewQuestion)
    assert question.question == "Вопрос Q-03 про SQL"
    assert await service.get_question(session_id, "Q-99") is None
    async with session_factory() as session:
        interview_session = await session.get(InterviewSession, session_id)
    assert interview_session.status == InterviewSessionStatus.QUESTIONS


async def test_repeated_generation_reuses_saved_questions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session(session_factory)
    llm, transport = llm_returning(question_payload(5))
    service = session_question_service(llm, session_factory)

    first = await service.generate_for_session(session_id)
    second = await service.generate_for_session(session_id)

    assert first == second
    assert len(transport.requests) == 1
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(SessionQuestion))
    assert count == 5


async def test_questions_are_isolated_per_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first_session = await create_session(session_factory)
    second_session = await create_session(session_factory)
    llm, _ = llm_returning(question_payload(2))
    service = session_question_service(llm, session_factory)

    await service.generate_for_session(first_session)

    assert await service.list_questions(second_session) == []
    assert await service.get_question(second_session, "Q-01") is None


async def test_session_without_analysis_is_rejected_before_llm_call(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session(session_factory, analyzed=False)
    llm, transport = llm_returning(question_payload())

    with pytest.raises(QuestionGenerationError):
        await session_question_service(llm, session_factory).generate_for_session(session_id)

    assert transport.requests == []


async def test_unknown_session_raises_database_error(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    llm, transport = llm_returning(question_payload())

    with pytest.raises(DatabaseError):
        await session_question_service(llm, session_factory).generate_for_session(999)

    assert transport.requests == []


async def test_llm_failure_saves_nothing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    session_id = await create_session(session_factory)
    llm, _ = make_openai_service(lambda request: error_response(503))
    service = session_question_service(llm, session_factory)

    with pytest.raises(LLMServiceError):
        await service.generate_for_session(session_id)

    assert await service.list_questions(session_id) == []
    async with session_factory() as session:
        interview_session = await session.get(InterviewSession, session_id)
    assert interview_session.status == InterviewSessionStatus.VACANCY_RESULT
