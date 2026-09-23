from collections import Counter
from pathlib import Path

import pytest

from app.knowledge.csv_repository import CsvKnowledgeRepository
from app.schemas.question import QuestionCategory
from app.services.knowledge_service import KnowledgeService

PROFESSIONS = ("analyst", "manager", "creative", "technical")
ORIGINAL_QUESTIONS = {
    "1": ("Чем REST отличается от SOAP?", QuestionCategory.TECHNICAL, False),
    "2": ("Расскажите о сложном проекте.", QuestionCategory.BEHAVIORAL, True),
    "3": ("Как вы собираете требования?", QuestionCategory.TECHNICAL, True),
    "4": ("Какие SQL JOIN вы знаете?", QuestionCategory.TECHNICAL, False),
}


@pytest.fixture(scope="module")
def items():
    return CsvKnowledgeRepository().load_questions()


def test_original_analyst_questions_are_preserved(items) -> None:
    by_id = {item.id: item for item in items}

    for item_id, (question, category, star_required) in ORIGINAL_QUESTIONS.items():
        item = by_id[item_id]
        assert (item.profession, item.question) == ("analyst", question)
        assert (item.category, item.star_required) == (category, star_required)
    assert by_id["1"].keywords == ["REST", "SOAP", "API"]
    assert by_id["4"].keywords == ["SQL", "JOIN"]


def test_every_row_is_parsed(items) -> None:
    lines = CsvKnowledgeRepository().questions_path.read_text(encoding="utf-8").splitlines()

    assert len(items) == len(lines) - 1


@pytest.mark.parametrize("profession", PROFESSIONS)
def test_each_profession_covers_all_categories(items, profession: str) -> None:
    categories = Counter(item.category for item in items if item.profession == profession)

    assert set(categories) == set(QuestionCategory)
    assert sum(categories.values()) >= 12
    assert any(item.star_required for item in items if item.profession == profession)


def test_no_duplicate_ids_or_questions(items) -> None:
    assert len({item.id for item in items}) == len(items)
    assert len({" ".join(item.question.lower().split()) for item in items}) == len(items)


@pytest.mark.parametrize(
    ("position", "profession"),
    [
        ("Бизнес-аналитик (Middle)", "analyst"),
        ("Project Manager", "manager"),
        ("Менеджер проектов", "manager"),
        ("Продакт-менеджер", "manager"),
        ("UI/UX дизайнер", "creative"),
        ("Копирайтер", "creative"),
        ("Python-разработчик", "technical"),
        ("QA Engineer", "technical"),
    ],
)
async def test_new_professions_are_found_by_vacancy_title(position: str, profession: str) -> None:
    items = await KnowledgeService().find_relevant(position, list(QuestionCategory), [])

    assert items
    assert {item.profession for item in items} == {profession}


async def test_keywords_rank_matching_questions_first() -> None:
    items = await KnowledgeService().find_relevant(
        "Python-разработчик", list(QuestionCategory), ["индексы", "SQL"]
    )

    assert items[0].question.startswith("Как устроены индексы")
    assert len({item.id for item in items}) == len(items) <= 20


async def test_skill_keywords_find_questions_of_other_professions() -> None:
    items = await KnowledgeService().find_relevant(None, [], ["Figma", "дизайн-система"])

    assert items
    assert {item.profession for item in items} == {"creative"}


async def test_unknown_profession_without_keywords_returns_nothing() -> None:
    assert await KnowledgeService().find_relevant("Повар", list(QuestionCategory), []) == []


async def test_professions_csv_adds_aliases_without_code(tmp_path: Path) -> None:
    (tmp_path / "questions.csv").write_text(
        "id,profession,category,question,difficulty,star_required,keywords\n"
        '1,ux_researcher,technical,"Как вы планируете глубинное интервью?",medium,false,"интервью"\n',
        encoding="utf-8",
    )
    (tmp_path / "professions.csv").write_text(
        'profession,title,aliases\nux_researcher,UX-исследователь,"ux researcher;ux-исследователь"\n',
        encoding="utf-8",
    )
    service = KnowledgeService(CsvKnowledgeRepository(tmp_path / "questions.csv"))

    items = await service.find_relevant("Senior UX Researcher", [], [])

    assert [item.id for item in items] == ["1"]
