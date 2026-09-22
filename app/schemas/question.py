from enum import Enum

from pydantic import Field, StrictBool

from app.schemas.base import SchemaModel

MIN_QUESTIONS = 1
MAX_QUESTIONS = 10


class QuestionCategory(str, Enum):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    SITUATIONAL = "situational"
    EXPERIENCE = "experience"


class QuestionDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class InterviewQuestion(SchemaModel):
    id: str = Field(min_length=1, description="Стабильный идентификатор вопроса.")
    question: str = Field(min_length=1, description="Текст вопроса.")
    category: QuestionCategory
    difficulty: QuestionDifficulty
    star_required: StrictBool = Field(
        default=False, description="Нужно ли отвечать по методике STAR."
    )


class QuestionSet(SchemaModel):
    questions: list[InterviewQuestion] = Field(
        min_length=MIN_QUESTIONS, max_length=MAX_QUESTIONS
    )
