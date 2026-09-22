import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.knowledge.csv_repository import CsvKnowledgeRepository, KnowledgeBaseError
from app.schemas.knowledge import KnowledgeItem
from app.schemas.question import QuestionCategory, QuestionDifficulty
from app.services.knowledge_service import DEFAULT_MAX_ITEMS, KnowledgeService

HEADER = "id,profession,category,question,difficulty,star_required,keywords\n"


def write_csv(tmp_path: Path, body: str, header: str = HEADER, encoding: str = "utf-8") -> Path:
    path = tmp_path / "questions.csv"
    path.write_text(header + body, encoding=encoding)
    return path


def service_for(path: Path, **kwargs: object) -> KnowledgeService:
    return KnowledgeService(CsvKnowledgeRepository(path), **kwargs)


def test_reads_project_csv() -> None:
    items = CsvKnowledgeRepository().load_questions()

    assert [item.id for item in items] == ["1", "2", "3", "4"]
    assert all(isinstance(item, KnowledgeItem) for item in items)
    rest = items[0]
    assert rest.profession == "analyst"
    assert rest.category is QuestionCategory.TECHNICAL
    assert rest.difficulty is QuestionDifficulty.EASY
    assert rest.star_required is False
    assert rest.keywords == ["REST", "SOAP", "API"]
    assert items[1].category is QuestionCategory.BEHAVIORAL
    assert items[1].star_required is True


def test_topic_categories_are_mapped_and_kept_as_keywords() -> None:
    items = {item.id: item for item in CsvKnowledgeRepository().load_questions()}

    assert items["3"].category is QuestionCategory.TECHNICAL
    assert "requirements" in [keyword.lower() for keyword in items["3"].keywords]
    assert items["4"].category is QuestionCategory.TECHNICAL
    assert items["4"].keywords == ["SQL", "JOIN"]


def test_header_is_detected_by_name_with_bom_and_any_column_order(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        'false,"SQL",easy,technical,"Что такое JOIN?",analyst,7\n',
        header="star_required,keywords,difficulty,category,question,profession,id\n",
        encoding="utf-8-sig",
    )

    [item] = CsvKnowledgeRepository(path).load_questions()

    assert item.id == "7"
    assert item.question == "Что такое JOIN?"
    assert item.keywords == ["SQL"]


def test_missing_column_raises_knowledge_base_error(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "1,analyst,technical,Q\n", header="id,profession,category,question\n")

    with pytest.raises(KnowledgeBaseError, match="missing columns"):
        CsvKnowledgeRepository(path).load_questions()


async def test_unreadable_knowledge_base_falls_back_to_empty(tmp_path: Path) -> None:
    service = service_for(tmp_path / "missing.csv")

    assert await service.find_relevant("Бизнес-аналитик", list(QuestionCategory), ["SQL"]) == []


@pytest.mark.parametrize(
    "position", ["Бизнес-аналитик (Middle)", "Business Analyst", "системный аналитик", "analyst"]
)
async def test_filters_by_profession(tmp_path: Path, position: str) -> None:
    path = write_csv(
        tmp_path,
        "1,analyst,technical,Вопрос аналитику,easy,false,BPMN\n"
        "2,developer,technical,Вопрос разработчику,easy,false,Python\n",
    )

    items = await service_for(path).find_relevant(position, [], [])

    assert [item.id for item in items] == ["1"]


async def test_unknown_profession_without_keywords_returns_nothing(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "1,analyst,technical,Вопрос,easy,false,BPMN\n")

    assert await service_for(path).find_relevant("Повар", list(QuestionCategory), []) == []
    assert await service_for(path).find_relevant(None, list(QuestionCategory), []) == []


async def test_category_raises_score(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        "1,analyst,technical,Технический вопрос,easy,false,\n"
        "2,analyst,behavioral,Поведенческий вопрос,easy,true,\n",
    )

    items = await service_for(path).find_relevant(
        "Аналитик", [QuestionCategory.BEHAVIORAL], []
    )

    assert [item.id for item in items] == ["2", "1"]


async def test_keywords_match_vacancy_skills(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        '1,analyst,technical,REST vs SOAP,easy,false,"REST,SOAP,API"\n'
        '2,analyst,technical,SQL JOIN,easy,false,"SQL,JOIN"\n'
        '3,developer,technical,Rapid prototyping,easy,false,"rapid"\n',
    )
    service = service_for(path)

    by_rest = await service.find_relevant(None, [], ["Интеграции через REST API"])
    by_sql = await service.find_relevant(None, [], ["sql"])
    by_word_part = await service.find_relevant(None, [], ["apidoc"])

    assert [item.id for item in by_rest] == ["1"]
    assert [item.id for item in by_sql] == ["2"]
    assert by_word_part == []


async def test_more_keyword_matches_rank_higher(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        '1,analyst,technical,Один навык,easy,false,"SQL"\n'
        '2,analyst,technical,Два навыка,easy,false,"SQL,BPMN"\n',
    )

    items = await service_for(path).find_relevant("Аналитик", [], ["SQL", "BPMN"])

    assert [item.id for item in items] == ["2", "1"]


async def test_duplicates_are_removed(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path,
        "1,analyst,technical,Как собрать требования?,easy,false,\n"
        "1,analyst,technical,Повтор id,easy,false,\n"
        "2,analyst,technical,  как собрать   требования? ,easy,false,\n"
        "3,analyst,technical,Другой вопрос,easy,false,\n",
    )

    items = await service_for(path).find_relevant("Аналитик", [], [])

    assert [item.id for item in items] == ["1", "3"]


async def test_result_is_limited(tmp_path: Path) -> None:
    rows = "".join(f"{i},analyst,technical,Вопрос {i},easy,false,\n" for i in range(30))
    path = write_csv(tmp_path, rows)

    assert len(await service_for(path).find_relevant("Аналитик", [], [])) == DEFAULT_MAX_ITEMS
    assert len(await service_for(path, max_items=5).find_relevant("Аналитик", [], [])) == 5


async def test_no_results_returns_empty_list_and_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = write_csv(tmp_path, "1,analyst,technical,Вопрос,easy,false,BPMN\n")

    with caplog.at_level(logging.INFO):
        items = await service_for(path).find_relevant("Повар", [], ["нож"])

    assert items == []
    assert "No relevant knowledge items found" in caplog.text


async def test_invalid_rows_are_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = write_csv(
        tmp_path,
        "1,analyst,technical,Нормальный вопрос,easy,false,\n"
        "2,analyst,technical,Плохая сложность,impossible,false,\n"
        "3,analyst,philosophy,Плохая категория,easy,false,\n"
        "4,analyst,technical,Плохой флаг,easy,maybe,\n"
        "5,analyst\n"
        ",analyst,technical,Без id,easy,false,\n"
        "6,analyst,behavioral,Ещё нормальный,hard,true,\n",
    )

    with caplog.at_level(logging.WARNING):
        items = CsvKnowledgeRepository(path).load_questions()

    assert [item.id for item in items] == ["1", "6"]
    assert caplog.text.count("Skipping invalid row") == 5


async def test_knowledge_is_loaded_once(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "1,analyst,technical,Вопрос,easy,false,\n")
    service = service_for(path)

    await service.find_relevant("Аналитик", [], [])
    path.write_text(HEADER, encoding="utf-8")

    assert len(await service.find_relevant("Аналитик", [], [])) == 1


def test_knowledge_item_is_strict_dto() -> None:
    item = KnowledgeItem(
        id="1",
        profession="analyst",
        category="technical",
        question="Вопрос",
        difficulty="easy",
    )

    assert item.keywords == []
    assert item.star_required is False
    assert KnowledgeItem.model_json_schema()["additionalProperties"] is False
    with pytest.raises(ValidationError):
        KnowledgeItem.model_validate(item.model_dump() | {"score": 5})
    with pytest.raises(ValidationError):
        KnowledgeItem.model_validate(item.model_dump() | {"category": "sql"})
