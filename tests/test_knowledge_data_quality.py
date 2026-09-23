import re
import shutil
from pathlib import Path

import pytest

from app.knowledge.csv_repository import KNOWLEDGE_BASE_DIR, CsvKnowledgeRepository
from app.knowledge.validate import main, validate_knowledge_base
from app.schemas.question import QuestionCategory
from app.services.knowledge_service import KnowledgeService


@pytest.fixture
def knowledge_dir(tmp_path: Path) -> Path:
    for name in ("questions.csv", "star_examples.csv", "checklists.csv", "professions.csv"):
        shutil.copy(KNOWLEDGE_BASE_DIR / name, tmp_path / name)
    return tmp_path


def append(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def test_project_knowledge_base_is_valid() -> None:
    assert validate_knowledge_base() == []


def test_cli_reports_valid_knowledge_base(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "Knowledge base is valid" in capsys.readouterr().out


def test_cli_reports_problems(knowledge_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    append(knowledge_dir / "questions.csv", '1,analyst,technical,"Новый вопрос?",easy,false,"SQL"')

    assert main([str(knowledge_dir)]) == 1
    assert "questions.csv:54: repeats id from line 2" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("file_name", "line", "expected"),
    [
        (
            "questions.csv",
            '900,analyst,technical,"Чем REST отличается от SOAP?",easy,false,"REST"',
            "duplicates the record from line 2",
        ),
        (
            "questions.csv",
            '901,ux_researcher,technical,"Как вы проводите интервью?",easy,false,"интервью"',
            "unknown profession 'ux_researcher'",
        ),
        (
            "questions.csv",
            '902,analyst,technical,"Вопрос без сложности?",,false,"SQL"',
            "column 'difficulty' is empty",
        ),
        (
            "questions.csv",
            '903,analyst,technical,"Вопрос со сломанными ключами?",easy,false,"SQL;;API"',
            "empty value between separators",
        ),
        (
            "questions.csv",
            '904,analyst,technical,"Вопрос с повтором ключей?",easy,false,"SQL;sql"',
            "repeated values",
        ),
        (
            "questions.csv",
            '905,analyst,technical,Вопрос, с запятой без кавычек?,easy,false,"SQL"',
            "expected 7 columns, got 8",
        ),
        (
            "questions.csv",
            '906,analyst,technical,"Вопрос?",expert,false,"SQL"',
            "invalid value",
        ),
        ("questions.csv", ",,,,,,", "empty row"),
        (
            "star_examples.csv",
            "STAR-900,analyst,behavioral,Вопрос?,Ситуация,Задача,Действия,,отчёт",
            "column 'result' is empty",
        ),
        (
            "checklists.csv",
            "CL-900,general,documents,Зонт,Возьмите зонт.,urgent,",
            "invalid value",
        ),
        (
            "checklists.csv",
            "CL-901,intern,documents,Пропуск,Закажите пропуск.,high,",
            "unknown profession 'intern'",
        ),
    ],
)
def test_broken_rows_are_reported(
    knowledge_dir: Path, file_name: str, line: str, expected: str
) -> None:
    append(knowledge_dir / file_name, line)

    errors = validate_knowledge_base(knowledge_dir)

    assert len(errors) == 1
    assert file_name in errors[0]
    assert expected in errors[0]


def test_non_utf8_file_is_reported(knowledge_dir: Path) -> None:
    text = (knowledge_dir / "checklists.csv").read_text(encoding="utf-8")
    (knowledge_dir / "checklists.csv").write_bytes(text.encode("cp1251"))

    assert validate_knowledge_base(knowledge_dir) == ["checklists.csv: file is not UTF-8 encoded"]


def test_wrong_header_and_missing_file_are_reported(knowledge_dir: Path) -> None:
    (knowledge_dir / "star_examples.csv").write_text("id,question\n", encoding="utf-8")
    (knowledge_dir / "checklists.csv").unlink()

    errors = validate_knowledge_base(knowledge_dir)

    assert len(errors) == 2
    assert errors[0].startswith("star_examples.csv: header must contain exactly")
    assert errors[1] == "checklists.csv: file not found"


GUIDE = Path(__file__).resolve().parent.parent / "docs" / "KNOWLEDGE_BASE_GUIDE.md"
EXAMPLE_FILES = ("professions.csv", "questions.csv", "star_examples.csv", "checklists.csv")


async def test_guide_example_profession_is_valid(knowledge_dir: Path) -> None:
    example = GUIDE.read_text(encoding="utf-8").split("## Пример: новая профессия", 1)[1]
    blocks = re.findall(r"```csv\n(.*?)```", example, flags=re.DOTALL)
    assert len(blocks) == len(EXAMPLE_FILES)
    for file_name, block in zip(EXAMPLE_FILES, blocks):
        for line in filter(None, map(str.strip, block.splitlines())):
            append(knowledge_dir / file_name, line)

    assert validate_knowledge_base(knowledge_dir) == []
    service = KnowledgeService(CsvKnowledgeRepository(knowledge_dir / "questions.csv"))
    items = await service.find_relevant("Senior UX Researcher", list(QuestionCategory), [])
    assert {item.profession for item in items} == {"ux_researcher"}


def test_new_profession_is_valid_once_registered(knowledge_dir: Path) -> None:
    append(knowledge_dir / "professions.csv", 'ux_researcher,UX-исследователь,"ux researcher"')
    append(
        knowledge_dir / "questions.csv",
        '901,ux_researcher,technical,"Как вы проводите интервью?",easy,false,"интервью"',
    )

    assert validate_knowledge_base(knowledge_dir) == []
