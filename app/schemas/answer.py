from enum import Enum

from pydantic import Field, StrictInt

from app.schemas.base import SchemaModel
from app.schemas.question import QuestionCategory

MIN_SCORE = 1
MAX_SCORE = 10


class StarElementStatus(str, Enum):
    FOUND = "found"
    MISSING = "missing"
    UNCLEAR = "unclear"


class StarAnalysis(SchemaModel):
    situation: StarElementStatus
    task: StarElementStatus
    action: StarElementStatus
    result: StarElementStatus


class AnswerAnalysis(SchemaModel):
    score: StrictInt = Field(ge=MIN_SCORE, le=MAX_SCORE, description="Оценка ответа 1..10.")
    question_type: QuestionCategory
    star: StarAnalysis
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    improved_answer: str | None = Field(
        description="Улучшенная версия ответа или null, если улучшать нечего."
    )
