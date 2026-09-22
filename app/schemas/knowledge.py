from pydantic import Field, StrictBool

from app.schemas.base import SchemaModel
from app.schemas.question import QuestionCategory, QuestionDifficulty


class KnowledgeItem(SchemaModel):
    """A row of knowledge_base/questions.csv."""

    id: str = Field(min_length=1)
    profession: str = Field(min_length=1)
    category: QuestionCategory
    question: str = Field(min_length=1)
    difficulty: QuestionDifficulty
    star_required: StrictBool = False
    keywords: list[str] = Field(default_factory=list)
