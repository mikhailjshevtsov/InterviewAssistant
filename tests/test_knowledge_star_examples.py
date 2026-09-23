import logging
from collections import Counter
from pathlib import Path

import pytest

from app.knowledge.csv_repository import CsvKnowledgeRepository, KnowledgeBaseError
from app.schemas.knowledge import StarExample
from app.schemas.question import QuestionCategory
from app.services.knowledge_service import KnowledgeService

HEADER = "id,profession,category,question,situation,task,action,result,keywords\n"
MINIMUM_PER_PROFESSION = {"analyst": 5, "manager": 3, "creative": 3, "technical": 3}


def repository_with(tmp_path: Path, body: str) -> CsvKnowledgeRepository:
    (tmp_path / "questions.csv").write_text(
        "id,profession,category,question,difficulty,star_required,keywords\n", encoding="utf-8"
    )
    (tmp_path / "star_examples.csv").write_text(HEADER + body, encoding="utf-8")
    return CsvKnowledgeRepository(tmp_path / "questions.csv")


def test_project_star_examples_are_complete() -> None:
    examples = CsvKnowledgeRepository().load_star_examples()

    counts = Counter(example.profession for example in examples)
    for profession, minimum in MINIMUM_PER_PROFESSION.items():
        assert counts[profession] >= minimum
    assert all(isinstance(example, StarExample) for example in examples)
    assert {example.category for example in examples} <= {
        QuestionCategory.BEHAVIORAL,
        QuestionCategory.SITUATIONAL,
        QuestionCategory.EXPERIENCE,
    }
    for example in examples:
        assert all([example.situation, example.task, example.action, example.result])
        assert example.keywords
    assert len({example.id for example in examples}) == len(examples)


def test_every_row_is_parsed() -> None:
    repository = CsvKnowledgeRepository()
    lines = repository.star_examples_path.read_text(encoding="utf-8").splitlines()

    assert len(repository.load_star_examples()) == len(lines) - 1


def test_invalid_rows_are_skipped(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    repository = repository_with(
        tmp_path,
        'S-1,analyst,behavioral,Вопрос,Ситуация,Задача,Действия,Результат,"BPMN;процесс"\n'
        "S-2,analyst,behavioral,Вопрос 2,Ситуация,Задача,Действия,,BPMN\n"
        "S-3,analyst,unknown,Вопрос 3,Ситуация,Задача,Действия,Результат,BPMN\n"
        ",,,,,,,,\n"
        "S-4,analyst\n",
    )

    with caplog.at_level(logging.WARNING):
        examples = repository.load_star_examples()

    assert [example.id for example in examples] == ["S-1"]
    assert examples[0].keywords == ["BPMN", "процесс"]
    assert caplog.text.count("Skipping invalid row") == 4


def test_missing_file_raises_and_service_falls_back(tmp_path: Path) -> None:
    repository = CsvKnowledgeRepository(tmp_path / "questions.csv")

    with pytest.raises(KnowledgeBaseError):
        repository.load_star_examples()


async def test_service_returns_empty_list_without_file(tmp_path: Path) -> None:
    service = KnowledgeService(CsvKnowledgeRepository(tmp_path / "questions.csv"))

    assert await service.find_star_examples("Аналитик", [QuestionCategory.BEHAVIORAL], []) == []


async def test_relevance_prefers_profession_category_and_keywords() -> None:
    examples = await KnowledgeService().find_star_examples(
        "Бизнес-аналитик",
        [QuestionCategory.BEHAVIORAL],
        ["Расскажите, как вы улучшили бизнес-процесс", "BPMN"],
    )

    assert [example.id for example in examples] == ["STAR-001", "STAR-002"]
    assert all(example.profession == "analyst" for example in examples)


async def test_limit_and_other_professions() -> None:
    service = KnowledgeService()

    manager = await service.find_star_examples(
        "Project manager", [QuestionCategory.BEHAVIORAL], [], limit=5
    )
    unknown = await service.find_star_examples("Повар", [QuestionCategory.BEHAVIORAL], [])

    assert {example.profession for example in manager} == {"manager"}
    assert len(manager) == 3
    assert unknown == []
