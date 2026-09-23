import csv
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from app.schemas.knowledge import (
    GENERAL_PROFESSION,
    ChecklistCategory,
    ChecklistItem,
    ChecklistPriority,
    KnowledgeItem,
    ProfessionProfile,
    StarExample,
)
from app.schemas.question import QuestionCategory

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
DEFAULT_QUESTIONS_PATH = KNOWLEDGE_BASE_DIR / "questions.csv"
STAR_EXAMPLES_FILE = "star_examples.csv"
CHECKLISTS_FILE = "checklists.csv"
PROFESSIONS_FILE = "professions.csv"

REQUIRED_COLUMNS = frozenset(
    {"id", "profession", "category", "question", "difficulty", "star_required", "keywords"}
)
STAR_EXAMPLE_COLUMNS = frozenset(
    {"id", "profession", "category", "question", "situation", "task", "action", "result", "keywords"}
)
CHECKLIST_COLUMNS = frozenset(
    {"id", "profession", "category", "title", "item", "priority", "keywords"}
)
PROFESSION_COLUMNS = frozenset({"profession", "title", "aliases"})

# ";" is the documented separator; "," is still accepted for the original questions.csv rows.
LIST_SEPARATOR_RE = re.compile(r"[;,]")
# questions.csv uses topic names as categories; they are mapped onto QuestionCategory
# and kept as keywords so the topic still takes part in keyword matching.
CATEGORY_ALIASES: dict[str, QuestionCategory] = {
    "sql": QuestionCategory.TECHNICAL,
    "requirements": QuestionCategory.TECHNICAL,
}
TRUE_VALUES = frozenset({"true", "1", "yes", "да"})
FALSE_VALUES = frozenset({"false", "0", "no", "нет", ""})

RowT = TypeVar("RowT")
Values = dict[str, str]


class KnowledgeBaseError(Exception):
    pass


def split_list(value: str) -> list[str]:
    return [part.strip() for part in LIST_SEPARATOR_RE.split(value) if part.strip()]


class CsvKnowledgeRepository:
    """Read-only access to the CSV files of one knowledge base directory."""

    def __init__(
        self,
        questions_path: Path = DEFAULT_QUESTIONS_PATH,
        *,
        star_examples_path: Path | None = None,
        checklists_path: Path | None = None,
        professions_path: Path | None = None,
    ):
        directory = questions_path.parent
        self.questions_path = questions_path
        self.star_examples_path = star_examples_path or directory / STAR_EXAMPLES_FILE
        self.checklists_path = checklists_path or directory / CHECKLISTS_FILE
        self.professions_path = professions_path or directory / PROFESSIONS_FILE

    def load_questions(self) -> list[KnowledgeItem]:
        return self._read(self.questions_path, REQUIRED_COLUMNS, self.parse_question)

    def load_star_examples(self) -> list[StarExample]:
        return self._read(self.star_examples_path, STAR_EXAMPLE_COLUMNS, self.parse_star_example)

    def load_checklists(self) -> list[ChecklistItem]:
        return self._read(self.checklists_path, CHECKLIST_COLUMNS, self.parse_checklist_item)

    def load_professions(self) -> list[ProfessionProfile]:
        return self._read(self.professions_path, PROFESSION_COLUMNS, self.parse_profession)

    def _read(
        self, path: Path, columns: frozenset[str], parse: Callable[[Values], RowT]
    ) -> list[RowT]:
        try:
            with path.open(encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                self._check_header(path, reader.fieldnames, columns)
                return [
                    item
                    for line_number, row in enumerate(reader, start=2)
                    if (item := self._parse_row(path, row, line_number, parse)) is not None
                ]
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            raise KnowledgeBaseError(f"Cannot read {path.name}") from exc

    @staticmethod
    def _check_header(path: Path, fieldnames: list[str] | None, columns: frozenset[str]) -> None:
        present = {name.strip().lower() for name in fieldnames or []}
        missing = columns - present
        if missing:
            raise KnowledgeBaseError(f"{path.name} is missing columns: {sorted(missing)}")

    @staticmethod
    def _parse_row(
        path: Path,
        row: dict[str | None, str | None],
        line_number: int,
        parse: Callable[[Values], RowT],
    ) -> RowT | None:
        values = {
            key.strip().lower(): (value or "").strip()
            for key, value in row.items()
            if isinstance(key, str)
        }
        try:
            return parse(values)
        except (KeyError, ValueError, ValidationError) as exc:
            logger.warning(
                "Skipping invalid row %s in %s (%s)", line_number, path.name, type(exc).__name__
            )
            return None

    @classmethod
    def parse_question(cls, values: Values) -> KnowledgeItem:
        raw_category = values["category"].lower()
        category = CATEGORY_ALIASES.get(raw_category) or QuestionCategory(raw_category)
        keywords = split_list(values["keywords"])
        if raw_category in CATEGORY_ALIASES and raw_category not in {
            keyword.lower() for keyword in keywords
        }:
            keywords.append(raw_category)
        return KnowledgeItem(
            id=values["id"],
            profession=values["profession"].lower(),
            category=category,
            question=values["question"],
            difficulty=values["difficulty"].lower(),
            star_required=cls._parse_bool(values["star_required"]),
            keywords=keywords,
        )

    @staticmethod
    def parse_star_example(values: Values) -> StarExample:
        return StarExample(
            id=values["id"],
            profession=values["profession"].lower(),
            category=QuestionCategory(values["category"].lower()),
            question=values["question"],
            situation=values["situation"],
            task=values["task"],
            action=values["action"],
            result=values["result"],
            keywords=split_list(values["keywords"]),
        )

    @staticmethod
    def parse_checklist_item(values: Values) -> ChecklistItem:
        return ChecklistItem(
            id=values["id"],
            profession=values["profession"].lower(),
            category=ChecklistCategory(values["category"].lower()),
            title=values["title"],
            item=values["item"],
            priority=ChecklistPriority(values["priority"].lower()),
            keywords=split_list(values["keywords"]),
        )

    @staticmethod
    def parse_profession(values: Values) -> ProfessionProfile:
        return ProfessionProfile(
            profession=values["profession"].lower(),
            title=values["title"],
            aliases=[alias.lower() for alias in split_list(values["aliases"])],
        )

    @staticmethod
    def _parse_bool(value: str) -> bool:
        normalized = value.lower()
        if normalized in TRUE_VALUES:
            return True
        if normalized in FALSE_VALUES:
            return False
        raise ValueError(f"Invalid boolean: {value!r}")
