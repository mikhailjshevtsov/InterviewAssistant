import pytest

from app.schemas.answer import AnswerAnalysis, StarAnalysis, StarElementStatus
from app.schemas.question import InterviewQuestion
from app.services.session_statistics import AnsweredQuestion, average_score, calculate_statistics

FOUND, MISSING, UNCLEAR = StarElementStatus.FOUND, StarElementStatus.MISSING, StarElementStatus.UNCLEAR


def answered(
    score: int, star_required: bool, star: tuple = (FOUND, FOUND, FOUND, MISSING)
) -> AnsweredQuestion:
    question = InterviewQuestion(
        id=f"Q-{score:02d}",
        question="Вопрос",
        category="behavioral" if star_required else "technical",
        difficulty="medium",
        star_required=star_required,
    )
    analysis = AnswerAnalysis(
        score=score,
        question_type=question.category,
        star=StarAnalysis(situation=star[0], task=star[1], action=star[2], result=star[3]),
        improved_answer=None,
    )
    return AnsweredQuestion(question, "ответ", analysis)


@pytest.mark.parametrize(
    ("scores", "expected"),
    [([7, 8, 6, 9], 7.5), ([7, 7, 8], 7.3), ([10], 10.0), ([1, 2], 1.5), ([], None)],
)
def test_average_score(scores: list[int], expected: float | None) -> None:
    assert average_score(scores) == expected


def test_statistics_count_only_star_questions() -> None:
    items = [
        answered(7, True, (FOUND, FOUND, FOUND, MISSING)),
        answered(8, True, (FOUND, UNCLEAR, FOUND, FOUND)),
        answered(6, False, (MISSING, MISSING, MISSING, MISSING)),
    ]

    statistics = calculate_statistics("Аналитик", 8, items)

    assert (statistics.answered_questions, statistics.total_questions) == (3, 8)
    assert statistics.average_score == 7.0
    star = statistics.star_statistics
    assert (star.answers, star.situation, star.task, star.action, star.result) == (2, 2, 1, 2, 1)


def test_no_star_questions_gives_no_star_statistics() -> None:
    statistics = calculate_statistics(None, 3, [answered(5, False)])

    assert statistics.star_statistics is None
    assert statistics.summary_fields()["position"] is None
