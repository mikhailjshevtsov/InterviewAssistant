from dataclasses import dataclass
from typing import Any

from app.schemas.answer import AnswerAnalysis, StarElementStatus
from app.schemas.question import InterviewQuestion
from app.schemas.session_summary import StarStatistics

STAR_ELEMENTS = ("situation", "task", "action", "result")


@dataclass(frozen=True, slots=True)
class AnsweredQuestion:
    question: InterviewQuestion
    answer: str
    analysis: AnswerAnalysis


@dataclass(frozen=True, slots=True)
class SessionStatistics:
    position: str | None
    answered_questions: int
    total_questions: int
    average_score: float | None
    star_statistics: StarStatistics | None

    def summary_fields(self) -> dict[str, Any]:
        """Fields of InterviewSummary that the application, not the LLM, is authoritative for."""
        return {
            "position": self.position,
            "answered_questions": self.answered_questions,
            "total_questions": self.total_questions,
            "average_score": self.average_score,
            "star_statistics": self.star_statistics,
        }


def average_score(scores: list[int]) -> float | None:
    if not scores:
        return None
    return round(sum(scores) / len(scores), 1)


def star_statistics(answered: list[AnsweredQuestion]) -> StarStatistics | None:
    star_analyses = [item.analysis.star for item in answered if item.question.star_required]
    if not star_analyses:
        return None
    found = {
        element: sum(getattr(star, element) == StarElementStatus.FOUND for star in star_analyses)
        for element in STAR_ELEMENTS
    }
    return StarStatistics(answers=len(star_analyses), **found)


def calculate_statistics(
    position: str | None, total_questions: int, answered: list[AnsweredQuestion]
) -> SessionStatistics:
    return SessionStatistics(
        position=position,
        answered_questions=len(answered),
        total_questions=total_questions,
        average_score=average_score([item.analysis.score for item in answered]),
        star_statistics=star_statistics(answered),
    )
