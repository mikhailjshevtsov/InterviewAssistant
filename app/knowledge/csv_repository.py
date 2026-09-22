import csv
import logging
from pathlib import Path

from pydantic import ValidationError

from app.schemas.knowledge import KnowledgeItem
from app.schemas.question import QuestionCategory

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_QUESTIONS_PATH = PROJECT_ROOT / "knowledge_base" / "questions.csv"

REQUIRED_COLUMNS = frozenset(
    {"id", "profession", "category", "question", "difficulty", "star_required", "keywords"}
)
# questions.csv uses topic names as categories; they are mapped onto QuestionCategory
# and kept as keywords so the topic still takes part in keyword matching.
CATEGORY_ALIASES: dict[str, QuestionCategory] = {
    "sql": QuestionCategory.TECHNICAL,
    "requirements": QuestionCategory.TECHNICAL,
}
TRUE_VALUES = frozenset({"true", "1", "yes", "да"})
FALSE_VALUES = frozenset({"false", "0", "no", "нет", ""})


class KnowledgeBaseError(Exception):
    pass


class CsvKnowledgeRepository:
    def __init__(self, questions_path: Path = DEFAULT_QUESTIONS_PATH):
        self.questions_path = questions_path

    def load_questions(self) -> list[KnowledgeItem]:
        try:
            with self.questions_path.open(encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                self._check_header(reader.fieldnames)
                return [
                    item
                    for line_number, row in enumerate(reader, start=2)
                    if (item := self._parse_row(row, line_number)) is not None
                ]
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            raise KnowledgeBaseError(f"Cannot read {self.questions_path.name}") from exc

    def _check_header(self, fieldnames: list[str] | None) -> None:
        columns = {name.strip().lower() for name in fieldnames or []}
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise KnowledgeBaseError(
                f"{self.questions_path.name} is missing columns: {sorted(missing)}"
            )

    def _parse_row(self, row: dict[str | None, str | None], line_number: int) -> KnowledgeItem | None:
        values = {
            key.strip().lower(): (value or "").strip()
            for key, value in row.items()
            if isinstance(key, str)
        }
        try:
            raw_category = values["category"].lower()
            category = CATEGORY_ALIASES.get(raw_category) or QuestionCategory(raw_category)
            keywords = [kw.strip() for kw in values["keywords"].split(",") if kw.strip()]
            if raw_category in CATEGORY_ALIASES and raw_category not in {
                kw.lower() for kw in keywords
            }:
                keywords.append(raw_category)
            return KnowledgeItem(
                id=values["id"],
                profession=values["profession"].lower(),
                category=category,
                question=values["question"],
                difficulty=values["difficulty"].lower(),
                star_required=self._parse_bool(values["star_required"]),
                keywords=keywords,
            )
        except (KeyError, ValueError, ValidationError) as exc:
            logger.warning(
                "Skipping invalid row %s in %s (%s)",
                line_number,
                self.questions_path.name,
                type(exc).__name__,
            )
            return None

    @staticmethod
    def _parse_bool(value: str) -> bool:
        normalized = value.lower()
        if normalized in TRUE_VALUES:
            return True
        if normalized in FALSE_VALUES:
            return False
        raise ValueError(f"Invalid boolean: {value!r}")
