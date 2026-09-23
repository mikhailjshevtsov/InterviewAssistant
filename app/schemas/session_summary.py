from typing import Self

from pydantic import Field, StrictInt, model_validator

from app.schemas.answer import MAX_SCORE, MIN_SCORE
from app.schemas.base import SchemaModel


class StarStatistics(SchemaModel):
    """How many answers to STAR questions contain each element."""

    answers: StrictInt = Field(ge=0, description="Количество ответов на STAR-вопросы.")
    situation: StrictInt = Field(ge=0)
    task: StrictInt = Field(ge=0)
    action: StrictInt = Field(ge=0)
    result: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def _elements_do_not_exceed_answers(self) -> Self:
        if max(self.situation, self.task, self.action, self.result) > self.answers:
            raise ValueError("STAR element count exceeds the number of STAR answers")
        return self


class InterviewSummary(SchemaModel):
    position: str | None = Field(description="Позиция из анализа вакансии.")
    answered_questions: StrictInt = Field(ge=0)
    total_questions: StrictInt = Field(ge=0)
    average_score: float | None = Field(
        ge=MIN_SCORE, le=MAX_SCORE, description="Средняя оценка; null, если ответов нет."
    )
    star_statistics: StarStatistics | None = Field(
        description="Статистика STAR; null, если STAR-вопросов среди отвеченных нет."
    )
    strong_sides: list[str] = Field(default_factory=list)
    weak_sides: list[str] = Field(default_factory=list)
    star_strengths: list[str] = Field(default_factory=list)
    star_gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    priority_topics: list[str] = Field(
        default_factory=list, description="Темы для повторения, по убыванию приоритета."
    )
    overall_summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def _statistics_are_consistent(self) -> Self:
        if self.answered_questions > self.total_questions:
            raise ValueError("answered_questions cannot exceed total_questions")
        if self.answered_questions == 0 and self.average_score is not None:
            raise ValueError("average_score must be null when there are no answers")
        if self.star_statistics and self.star_statistics.answers > self.answered_questions:
            raise ValueError("STAR answers cannot exceed answered_questions")
        return self
