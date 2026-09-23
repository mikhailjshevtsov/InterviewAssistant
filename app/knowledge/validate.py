"""Validates the knowledge base CSV files.

Run from the project root: python -m app.knowledge.validate [directory]
"""

import csv
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.knowledge.csv_repository import (
    CHECKLIST_COLUMNS,
    CHECKLISTS_FILE,
    GENERAL_PROFESSION,
    KNOWLEDGE_BASE_DIR,
    PROFESSION_COLUMNS,
    PROFESSIONS_FILE,
    REQUIRED_COLUMNS,
    STAR_EXAMPLE_COLUMNS,
    STAR_EXAMPLES_FILE,
    CsvKnowledgeRepository,
    split_list,
)

QUESTIONS_FILE = "questions.csv"


@dataclass(frozen=True, slots=True)
class _FileSpec:
    name: str
    columns: frozenset[str]
    key: str
    required: tuple[str, ...]
    parse: Callable[[dict[str, str]], BaseModel]
    list_column: str
    list_required: bool
    duplicate_key: Callable[[dict[str, str]], str] | None


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


FILE_SPECS = (
    _FileSpec(
        PROFESSIONS_FILE,
        PROFESSION_COLUMNS,
        "profession",
        ("profession", "title", "aliases"),
        CsvKnowledgeRepository.parse_profession,
        "aliases",
        True,
        None,
    ),
    _FileSpec(
        QUESTIONS_FILE,
        REQUIRED_COLUMNS,
        "id",
        ("id", "profession", "category", "question", "difficulty", "star_required", "keywords"),
        CsvKnowledgeRepository.parse_question,
        "keywords",
        True,
        lambda row: _normalize(row["question"]),
    ),
    _FileSpec(
        STAR_EXAMPLES_FILE,
        STAR_EXAMPLE_COLUMNS,
        "id",
        tuple(sorted(STAR_EXAMPLE_COLUMNS)),
        CsvKnowledgeRepository.parse_star_example,
        "keywords",
        True,
        lambda row: _normalize(row["situation"]),
    ),
    _FileSpec(
        CHECKLISTS_FILE,
        CHECKLIST_COLUMNS,
        "id",
        ("id", "profession", "category", "title", "item", "priority"),
        CsvKnowledgeRepository.parse_checklist_item,
        "keywords",
        False,
        lambda row: f"{row['profession']}|{row['category']}|{_normalize(row['title'])}",
    ),
)


def _read_rows(path: Path, spec: _FileSpec, errors: list[str]) -> list[tuple[int, dict[str, str]]]:
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except OSError:
        errors.append(f"{spec.name}: file not found")
        return []
    except UnicodeDecodeError:
        errors.append(f"{spec.name}: file is not UTF-8 encoded")
        return []
    try:
        reader = csv.reader(text.splitlines())
        header = [name.strip().lower() for name in next(reader, [])]
        rows = list(enumerate(reader, start=2))
    except csv.Error as exc:
        errors.append(f"{spec.name}: broken CSV ({exc})")
        return []

    if set(header) != spec.columns or len(header) != len(spec.columns):
        errors.append(
            f"{spec.name}: header must contain exactly {sorted(spec.columns)}, got {header}"
        )
        return []
    result = []
    for line, row in rows:
        if not any(value.strip() for value in row):
            errors.append(f"{spec.name}:{line}: empty row")
            continue
        if len(row) != len(header):
            errors.append(
                f"{spec.name}:{line}: expected {len(header)} columns, got {len(row)} "
                "(check quotes and commas)"
            )
            continue
        result.append((line, {name: value.strip() for name, value in zip(header, row)}))
    return result


def _check_row(
    spec: _FileSpec,
    line: int,
    row: dict[str, str],
    professions: set[str],
    seen: dict[str, dict[str, int]],
    errors: list[str],
) -> None:
    where = f"{spec.name}:{line}"
    empty = [column for column in spec.required if not row[column]]
    for column in empty:
        errors.append(f"{where}: column '{column}' is empty")
    if not empty:
        try:
            spec.parse(row)
        except (KeyError, ValueError, ValidationError) as exc:
            detail = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
            errors.append(f"{where}: invalid value ({detail})")

    raw_list = row[spec.list_column]
    items = split_list(raw_list)
    if spec.list_required and not items:
        errors.append(f"{where}: column '{spec.list_column}' needs at least one value")
    if raw_list and len(items) != len([part for part in raw_list.replace(",", ";").split(";")]):
        errors.append(f"{where}: column '{spec.list_column}' has an empty value between separators")
    if len({_normalize(item) for item in items}) != len(items):
        errors.append(f"{where}: column '{spec.list_column}' has repeated values")

    if spec.name != PROFESSIONS_FILE:
        allowed = professions | ({GENERAL_PROFESSION} if spec.name == CHECKLISTS_FILE else set())
        if row["profession"].lower() not in allowed:
            errors.append(
                f"{where}: unknown profession '{row['profession']}' "
                f"(declare it in {PROFESSIONS_FILE})"
            )

    for label, key in (("id", row[spec.key].lower()), ("duplicate", spec.duplicate_key and spec.duplicate_key(row))):
        if not key:
            continue
        first = seen[label].setdefault(key, line)
        if first != line:
            message = "repeats id" if label == "id" else "duplicates the record"
            errors.append(f"{where}: {message} from line {first}")


def validate_knowledge_base(directory: Path = KNOWLEDGE_BASE_DIR) -> list[str]:
    """Returns human-readable problems; an empty list means the knowledge base is valid."""
    errors: list[str] = []
    professions: set[str] = set()
    for spec in FILE_SPECS:
        rows = _read_rows(directory / spec.name, spec, errors)
        seen: dict[str, dict[str, int]] = {"id": {}, "duplicate": {}}
        for line, row in rows:
            _check_row(spec, line, row, professions, seen, errors)
        if spec.name == PROFESSIONS_FILE:
            professions = {row["profession"].lower() for _, row in rows if row["profession"]}
    return errors


def main(argv: list[str]) -> int:
    directory = Path(argv[0]) if argv else KNOWLEDGE_BASE_DIR
    errors = validate_knowledge_base(directory)
    if errors:
        print(f"Knowledge base has {len(errors)} problem(s):")
        for error in errors:
            print(f"  - {error}")
        return 1
    repository = CsvKnowledgeRepository(directory / QUESTIONS_FILE)
    print(
        "Knowledge base is valid: "
        f"{len(repository.load_professions())} professions, "
        f"{len(repository.load_questions())} questions, "
        f"{len(repository.load_star_examples())} STAR examples, "
        f"{len(repository.load_checklists())} checklist items."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
