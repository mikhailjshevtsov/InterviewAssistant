from enum import Enum

from pydantic import Field, StrictBool

from app.schemas.base import SchemaModel
from app.schemas.question import QuestionCategory, QuestionDifficulty

# Checklist rows with this profession apply to every candidate.
GENERAL_PROFESSION = "general"


class KnowledgeItem(SchemaModel):
    """A row of knowledge_base/questions.csv."""

    id: str = Field(min_length=1)
    profession: str = Field(min_length=1)
    category: QuestionCategory
    question: str = Field(min_length=1)
    difficulty: QuestionDifficulty
    star_required: StrictBool = False
    keywords: list[str] = Field(default_factory=list)


class StarExample(SchemaModel):
    """A row of knowledge_base/star_examples.csv: a reference answer structure, not candidate facts."""

    id: str = Field(min_length=1)
    profession: str = Field(min_length=1)
    category: QuestionCategory
    question: str = Field(min_length=1)
    situation: str = Field(min_length=1)
    task: str = Field(min_length=1)
    action: str = Field(min_length=1)
    result: str = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)


class ChecklistCategory(str, Enum):
    """Interview stages in the order they are shown to the user."""

    BEFORE_INTERVIEW = "before_interview"
    DOCUMENTS = "documents"
    APPEARANCE = "appearance"
    FINAL_CHECK = "final_check"
    DURING_INTERVIEW = "during_interview"
    END_INTERVIEW = "end_interview"
    AFTER_INTERVIEW = "after_interview"


class ChecklistPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ChecklistItem(SchemaModel):
    """A row of knowledge_base/checklists.csv."""

    id: str = Field(min_length=1)
    profession: str = Field(min_length=1)
    category: ChecklistCategory
    title: str = Field(min_length=1)
    item: str = Field(min_length=1)
    priority: ChecklistPriority
    keywords: list[str] = Field(default_factory=list)


class ProfessionProfile(SchemaModel):
    """A row of knowledge_base/professions.csv."""

    profession: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    title: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
