import pytest
from pydantic import ValidationError

from app.schemas.session_summary import InterviewSummary, StarStatistics

VALID = {
    "position": "Бизнес-аналитик",
    "answered_questions": 6,
    "total_questions": 8,
    "average_score": 7.4,
    "star_statistics": {"answers": 3, "situation": 3, "task": 2, "action": 3, "result": 1},
    "strong_sides": ["Структурирует требования"],
    "weak_sides": ["Мало измеримых результатов"],
    "star_strengths": ["Action описан подробно"],
    "star_gaps": ["Result часто отсутствует"],
    "recommendations": ["Добавляйте метрики"],
    "priority_topics": ["SQL JOIN", "BPMN"],
    "overall_summary": "Хорошая база, нужно больше конкретики в результатах.",
}


def make(**changes) -> InterviewSummary:
    return InterviewSummary.model_validate(VALID | changes)


def test_valid_summary() -> None:
    summary = make()

    assert summary.average_score == 7.4
    assert summary.star_statistics == StarStatistics(
        answers=3, situation=3, task=2, action=3, result=1
    )
    assert InterviewSummary.model_validate_json(summary.model_dump_json()) == summary


def test_empty_lists_are_allowed() -> None:
    summary = make(
        star_statistics=None,
        strong_sides=[],
        weak_sides=[],
        star_strengths=[],
        star_gaps=[],
        recommendations=[],
        priority_topics=[],
    )

    assert summary.recommendations == []


def test_no_answers_scenario() -> None:
    summary = make(answered_questions=0, average_score=None, star_statistics=None)

    assert summary.average_score is None
    with pytest.raises(ValidationError):
        make(answered_questions=0, average_score=5.0, star_statistics=None)


@pytest.mark.parametrize("score", [1, 1.0, 5.5, 10])
def test_average_score_in_range(score: float) -> None:
    assert make(average_score=score).average_score == score


@pytest.mark.parametrize("score", [0, 0.9, 10.1, 11])
def test_average_score_out_of_range(score: float) -> None:
    with pytest.raises(ValidationError):
        make(average_score=score)


@pytest.mark.parametrize(
    "changes",
    [
        {"answered_questions": -1},
        {"total_questions": -1},
        {"answered_questions": 9, "total_questions": 8},
        {"star_statistics": {"answers": 7, "situation": 0, "task": 0, "action": 0, "result": 0}},
        {"star_statistics": {"answers": 2, "situation": 3, "task": 0, "action": 0, "result": 0}},
        {"overall_summary": ""},
        {"answered_questions": "6"},
    ],
)
def test_invalid_statistics(changes: dict) -> None:
    with pytest.raises(ValidationError):
        make(**changes)


def test_answered_can_equal_total() -> None:
    assert make(answered_questions=8, total_questions=8).answered_questions == 8


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        make(telegram_id=123)
    with pytest.raises(ValidationError):
        make(star_statistics=VALID["star_statistics"] | {"extra": 1})


def test_structured_output_schema_is_strict() -> None:
    from openai.lib._pydantic import to_strict_json_schema

    schema = to_strict_json_schema(InterviewSummary)

    assert set(schema["required"]) == set(InterviewSummary.model_fields)
    assert schema["additionalProperties"] is False
