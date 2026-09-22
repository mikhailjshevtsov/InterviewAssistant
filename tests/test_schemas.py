import typing

import pytest
from pydantic import BaseModel, ValidationError

from app.database.models import Base
from app.schemas import (
    AnswerAnalysis,
    InterviewQuestion,
    QuestionCategory,
    QuestionDifficulty,
    QuestionSet,
    StarAnalysis,
    StarElementStatus,
    VacancyAnalysis,
)
from app.services.answer_service import AnswerService
from app.services.openai_service import OpenAIService
from app.services.question_service import QuestionService
from app.services.vacancy_service import VacancyService

VACANCY_EXAMPLE = {
    "position": "Бизнес-аналитик",
    "company": None,
    "hard_skills": ["SQL", "BPMN", "REST API"],
    "soft_skills": ["коммуникация"],
    "experience": ["сбор требований"],
    "responsibilities": ["анализ требований"],
    "interview_topics": ["SQL", "системный анализ"],
}


def make_question(index: int = 1, **overrides: object) -> InterviewQuestion:
    data = {
        "id": f"q{index}",
        "question": "Расскажите о сложном проекте",
        "category": "behavioral",
        "difficulty": "medium",
    } | overrides
    return InterviewQuestion.model_validate(data)


def make_star(status: StarElementStatus = StarElementStatus.FOUND) -> StarAnalysis:
    return StarAnalysis(situation=status, task=status, action=status, result=status)


def make_answer_analysis(**overrides: object) -> AnswerAnalysis:
    data = {
        "score": 7,
        "question_type": "behavioral",
        "star": make_star(),
        "improved_answer": "Улучшенный ответ",
    } | overrides
    return AnswerAnalysis.model_validate(data)


def test_valid_vacancy_analysis() -> None:
    analysis = VacancyAnalysis.model_validate(VACANCY_EXAMPLE)

    assert analysis.position == "Бизнес-аналитик"
    assert analysis.hard_skills == ["SQL", "BPMN", "REST API"]
    assert analysis.interview_topics == ["SQL", "системный анализ"]


def test_vacancy_analysis_allows_null_company() -> None:
    assert VacancyAnalysis(position="QA", company=None).company is None


def test_vacancy_analysis_lists_default_to_empty() -> None:
    analysis = VacancyAnalysis(position=None, company=None)

    assert analysis.hard_skills == []
    assert analysis.soft_skills == []
    assert analysis.experience == []
    assert analysis.responsibilities == []
    assert analysis.interview_topics == []


def test_vacancy_analysis_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        VacancyAnalysis.model_validate(VACANCY_EXAMPLE | {"salary": "100k"})


def test_interview_question_is_created() -> None:
    question = make_question(star_required=True)

    assert question.id == "q1"
    assert question.category is QuestionCategory.BEHAVIORAL
    assert question.difficulty is QuestionDifficulty.MEDIUM
    assert question.star_required is True
    assert make_question().star_required is False


def test_invalid_category_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_question(category="philosophical")


def test_invalid_difficulty_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_question(difficulty="impossible")


@pytest.mark.parametrize("count", [1, 10])
def test_question_set_accepts_allowed_sizes(count: int) -> None:
    question_set = QuestionSet(questions=[make_question(i) for i in range(count)])

    assert len(question_set.questions) == count


@pytest.mark.parametrize("count", [0, 11])
def test_question_set_rejects_invalid_sizes(count: int) -> None:
    with pytest.raises(ValidationError):
        QuestionSet(questions=[make_question(i) for i in range(count)])


@pytest.mark.parametrize("score", [1, 10])
def test_answer_analysis_accepts_score_bounds(score: int) -> None:
    assert make_answer_analysis(score=score).score == score


@pytest.mark.parametrize("score", [0, 11, "7", 7.5])
def test_answer_analysis_rejects_invalid_score(score: object) -> None:
    with pytest.raises(ValidationError):
        make_answer_analysis(score=score)


@pytest.mark.parametrize("status", ["found", "missing", "unclear"])
def test_star_analysis_accepts_all_statuses(status: str) -> None:
    star = StarAnalysis.model_validate(
        {"situation": status, "task": status, "action": status, "result": status}
    )

    assert star.situation is StarElementStatus(status)


def test_star_analysis_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        StarAnalysis.model_validate(
            {"situation": "maybe", "task": "found", "action": "found", "result": "found"}
        )


def test_improved_answer_can_be_none() -> None:
    assert make_answer_analysis(improved_answer=None).improved_answer is None


def test_list_defaults_are_not_shared() -> None:
    first = VacancyAnalysis(position=None, company=None)
    second = VacancyAnalysis(position=None, company=None)
    first.hard_skills.append("SQL")

    first_answer = make_answer_analysis()
    second_answer = make_answer_analysis()
    first_answer.strengths.append("структура")

    assert second.hard_skills == []
    assert second_answer.strengths == []


def test_answer_analysis_round_trips_through_json() -> None:
    analysis = make_answer_analysis(strengths=["конкретика"])

    restored = AnswerAnalysis.model_validate_json(analysis.model_dump_json())

    assert restored == analysis
    assert restored.question_type is QuestionCategory.BEHAVIORAL


@pytest.mark.parametrize(
    "model",
    [VacancyAnalysis, InterviewQuestion, QuestionSet, StarAnalysis, AnswerAnalysis],
)
def test_json_schema_is_generated(model: type[BaseModel]) -> None:
    schema = model.model_json_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(model.model_fields)


def test_json_schema_contains_constraints() -> None:
    question_set_schema = QuestionSet.model_json_schema()
    answer_schema = AnswerAnalysis.model_json_schema()

    questions = question_set_schema["properties"]["questions"]
    assert (questions["minItems"], questions["maxItems"]) == (1, 10)
    assert question_set_schema["$defs"]["QuestionCategory"]["enum"] == [
        "technical",
        "behavioral",
        "situational",
        "experience",
    ]
    score = answer_schema["properties"]["score"]
    assert (score["minimum"], score["maximum"]) == (1, 10)
    assert answer_schema["$defs"]["StarElementStatus"]["enum"] == [
        "found",
        "missing",
        "unclear",
    ]


@pytest.mark.parametrize(
    "model",
    [VacancyAnalysis, InterviewQuestion, QuestionSet, StarAnalysis, AnswerAnalysis],
)
def test_dto_is_not_mixed_with_orm(model: type[BaseModel]) -> None:
    assert not issubclass(model, Base)
    assert not hasattr(model, "__table__")


@pytest.mark.parametrize(
    ("method", "expected_return"),
    [
        (OpenAIService.analyze_vacancy, VacancyAnalysis),
        (OpenAIService.generate_questions, QuestionSet),
        (OpenAIService.analyze_answer, AnswerAnalysis),
        (VacancyService.analyze, VacancyAnalysis),
        (QuestionService.generate, QuestionSet),
        (AnswerService.analyze, AnswerAnalysis),
    ],
)
def test_service_contracts_are_typed(method: object, expected_return: type) -> None:
    hints = typing.get_type_hints(method)

    assert hints["return"] is expected_return
    assert typing.Any not in hints.values()


async def test_openai_stub_is_not_implemented() -> None:
    analysis = VacancyAnalysis.model_validate(VACANCY_EXAMPLE)

    with pytest.raises(NotImplementedError):
        await QuestionService(OpenAIService()).generate(analysis, [make_question()])
    with pytest.raises(NotImplementedError):
        await AnswerService(OpenAIService()).analyze(make_question(), "ответ", analysis)
