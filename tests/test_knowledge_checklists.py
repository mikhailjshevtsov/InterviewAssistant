import logging
from collections import Counter
from pathlib import Path

import pytest

from app.knowledge.csv_repository import CsvKnowledgeRepository, KnowledgeBaseError
from app.schemas.knowledge import GENERAL_PROFESSION, ChecklistCategory, ChecklistPriority
from app.services.checklist_service import ChecklistService

HEADER = "id,profession,category,title,item,priority,keywords\n"


def repository_with(tmp_path: Path, body: str) -> CsvKnowledgeRepository:
    (tmp_path / "checklists.csv").write_text(HEADER + body, encoding="utf-8")
    return CsvKnowledgeRepository(tmp_path / "questions.csv")


def test_project_checklists_cover_every_category() -> None:
    items = CsvKnowledgeRepository().load_checklists()

    general = Counter(item.category for item in items if item.profession == GENERAL_PROFESSION)
    assert set(general) == set(ChecklistCategory)
    assert min(general.values()) >= 5
    assert len({item.id for item in items}) == len(items)
    assert all(item.title and item.item for item in items)


def test_every_row_is_parsed() -> None:
    repository = CsvKnowledgeRepository()
    lines = repository.checklists_path.read_text(encoding="utf-8").splitlines()

    assert len(repository.load_checklists()) == len(lines) - 1


def test_invalid_rows_are_skipped(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    repository = repository_with(
        tmp_path,
        "C-1,general,documents,Паспорт,Возьмите паспорт.,high,документы\n"
        "C-2,general,unknown,Пункт,Текст.,high,\n"
        "C-3,general,documents,Пункт,Текст.,urgent,\n"
        "C-4,general,documents,,Текст.,low,\n"
        ",,,,,,\n",
    )

    with caplog.at_level(logging.WARNING):
        items = repository.load_checklists()

    assert [item.id for item in items] == ["C-1"]
    assert items[0].keywords == ["документы"]
    assert caplog.text.count("Skipping invalid row") == 4


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(KnowledgeBaseError):
        CsvKnowledgeRepository(tmp_path / "questions.csv").load_checklists()


async def test_service_orders_general_items_first_then_priority(tmp_path: Path) -> None:
    service = ChecklistService(
        repository_with(
            tmp_path,
            "C-1,analyst,documents,Портфолио,Кейсы.,high,\n"
            "C-2,general,documents,Ручка,Возьмите ручку.,low,\n"
            "C-3,general,documents,Паспорт,Возьмите паспорт.,high,\n"
            "C-4,general,appearance,Одежда,Опрятная одежда.,medium,\n",
        )
    )

    items = await service.get_items(ChecklistCategory.DOCUMENTS)

    assert [item.id for item in items] == ["C-3", "C-2", "C-1"]
    assert await service.list_categories() == [
        ChecklistCategory.DOCUMENTS,
        ChecklistCategory.APPEARANCE,
    ]


async def test_service_lists_project_categories_in_display_order() -> None:
    service = ChecklistService()

    assert await service.list_categories() == list(ChecklistCategory)
    items = await service.get_items(ChecklistCategory.BEFORE_INTERVIEW)
    assert items[0].profession == GENERAL_PROFESSION
    assert items[0].priority is ChecklistPriority.HIGH


async def test_service_returns_profession_titles() -> None:
    titles = await ChecklistService().profession_titles()

    assert set(titles) == {"analyst", "manager", "creative", "technical"}
    assert all(titles.values())


async def test_service_falls_back_to_empty_lists(tmp_path: Path) -> None:
    service = ChecklistService(CsvKnowledgeRepository(tmp_path / "questions.csv"))

    assert await service.list_categories() == []
    assert await service.get_items(ChecklistCategory.DOCUMENTS) == []
    assert await service.profession_titles() == {}
