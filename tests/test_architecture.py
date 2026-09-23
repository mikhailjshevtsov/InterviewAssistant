import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
BOT_FILES = sorted((APP_DIR / "bot").rglob("*.py"))
SERVICE_FILES = sorted(
    path
    for path in (APP_DIR / "services").glob("*.py")
    if path.name != "openai_service.py"
)
OPENAI_NAMES = {"openai", "AsyncOpenAI", "OpenAI"}


def imported_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(alias.name for alias in node.names)
    return names


def imports_openai(names: set[str]) -> bool:
    return any(name.split(".")[0] in OPENAI_NAMES for name in names)


@pytest.mark.parametrize("path", BOT_FILES, ids=lambda path: path.name)
def test_bot_layer_does_not_import_openai_or_database_internals(path: Path) -> None:
    names = imported_names(path)

    assert not imports_openai(names)
    assert not any(name.startswith("sqlalchemy") for name in names)
    assert not any(name.startswith("app.database.repositories") for name in names)


@pytest.mark.parametrize("path", SERVICE_FILES, ids=lambda path: path.name)
def test_only_openai_service_imports_openai(path: Path) -> None:
    assert not imports_openai(imported_names(path))


def test_openai_service_uses_async_client() -> None:
    names = imported_names(APP_DIR / "services" / "openai_service.py")

    assert "AsyncOpenAI" in names
    assert "OpenAI" not in names


KNOWLEDGE_FILES = [
    APP_DIR / "services" / "knowledge_service.py",
    APP_DIR / "services" / "checklist_service.py",
    *sorted((APP_DIR / "knowledge").glob("*.py")),
]
FORBIDDEN_IN_KNOWLEDGE = ("sqlalchemy", "aiogram", "app.database", "app.bot", "app.services.openai")


@pytest.mark.parametrize("path", KNOWLEDGE_FILES, ids=lambda path: path.name)
def test_knowledge_layer_is_isolated(path: Path) -> None:
    names = imported_names(path)

    assert not imports_openai(names)
    assert not any(name.startswith(FORBIDDEN_IN_KNOWLEDGE) for name in names)


@pytest.mark.parametrize("path", BOT_FILES, ids=lambda path: path.name)
def test_bot_layer_does_not_read_knowledge_base(path: Path) -> None:
    names = imported_names(path)

    assert "csv" not in names
    assert not any(name.startswith("app.knowledge") for name in names)


def test_question_service_does_not_create_openai_client() -> None:
    source = (APP_DIR / "services" / "question_service.py").read_text(encoding="utf-8")

    assert "AsyncOpenAI" not in source
    assert "responses.parse" not in source


def test_dtos_are_not_orm_models() -> None:
    from app.database.models import Base
    from app.schemas import KnowledgeItem, QuestionSet

    for dto in (KnowledgeItem, QuestionSet):
        assert not issubclass(dto, Base)


ANSWER_FLOW_HANDLERS = [APP_DIR / "bot" / "handlers" / name for name in ("answers.py", "questions.py")]
LOGIC_IN_HANDLERS = ("app.services.answer_validator", "app.services.prompt_context", "app.schemas.answer")


@pytest.mark.parametrize("path", ANSWER_FLOW_HANDLERS, ids=lambda path: path.name)
def test_answer_handlers_only_orchestrate(path: Path) -> None:
    names = imported_names(path)
    source = path.read_text(encoding="utf-8")

    assert not imports_openai(names)
    assert not any(name.startswith(("sqlalchemy", "app.database.repositories", "csv")) for name in names)
    assert "app.database.models" not in names
    assert "analyze_answer" not in source
    assert ".score" not in source
    assert "StarElementStatus" not in source


def test_answer_service_is_framework_free() -> None:
    names = imported_names(APP_DIR / "services" / "answer_service.py")
    source = (APP_DIR / "services" / "answer_service.py").read_text(encoding="utf-8")

    assert not any(name.startswith(("aiogram", "app.bot")) for name in names)
    assert not imports_openai(names)
    assert "AsyncOpenAI" not in source
    assert "responses.parse" not in source
    assert "json.loads" not in source


def test_answer_analysis_is_single_openai_call_site() -> None:
    sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in APP_DIR.rglob("*.py")
        if "responses.parse" in path.read_text(encoding="utf-8")
    }

    assert list(sources) == ["openai_service.py"]
    assert sources["openai_service.py"].count("AsyncOpenAI(") == 1


def test_answer_dtos_are_not_orm_models() -> None:
    from app.database.models import Base
    from app.schemas.answer import AnswerAnalysis, StarAnalysis

    for dto in (AnswerAnalysis, StarAnalysis):
        assert not issubclass(dto, Base)


def test_summary_handler_only_orchestrates() -> None:
    path = APP_DIR / "bot" / "handlers" / "summary.py"
    names = imported_names(path)
    source = path.read_text(encoding="utf-8")

    assert not imports_openai(names)
    assert not any(name.startswith(("sqlalchemy", "app.database.repositories", "csv")) for name in names)
    assert "app.database.models" not in names
    assert "app.services.session_statistics" not in names
    for forbidden in ("summarize_session", "sum(", "len(", "average", "StarElementStatus", "recommendations"):
        assert forbidden not in source


def test_session_summary_service_is_framework_free() -> None:
    path = APP_DIR / "services" / "session_summary_service.py"
    names = imported_names(path)
    source = path.read_text(encoding="utf-8")

    assert not any(name.startswith(("aiogram", "app.bot")) for name in names)
    assert not imports_openai(names)
    assert "AsyncOpenAI" not in source and "responses.parse" not in source
    assert "json.loads" not in source
    assert "AnswerService" not in source and "analyze_answer" not in source


def test_session_statistics_is_pure() -> None:
    names = imported_names(APP_DIR / "services" / "session_statistics.py")

    assert not any(
        name.startswith(("aiogram", "sqlalchemy", "app.database", "app.bot", "app.services.openai"))
        for name in names
    )
    assert not imports_openai(names)


@pytest.mark.parametrize("path", KNOWLEDGE_FILES, ids=lambda path: path.name)
def test_knowledge_base_is_read_only(path: Path) -> None:
    source = path.read_text(encoding="utf-8")

    for forbidden in ("csv.writer", "DictWriter", "write_text", "write_bytes", ".write(", '"w"', '"a"'):
        assert forbidden not in source


def test_checklists_handler_only_orchestrates() -> None:
    path = APP_DIR / "bot" / "handlers" / "checklists.py"
    names = imported_names(path)
    source = path.read_text(encoding="utf-8")

    assert not imports_openai(names)
    assert not any(
        name.startswith(("sqlalchemy", "app.database", "app.knowledge", "csv")) for name in names
    )
    assert "InterviewState" not in source and "set_state" not in source
    assert "load_checklists" not in source and "sorted(" not in source


def test_answer_service_gets_star_examples_only_through_knowledge_service() -> None:
    names = imported_names(APP_DIR / "services" / "answer_service.py")

    assert "app.services.knowledge_service" in names
    assert not any(name.startswith("app.knowledge") for name in names)
    assert "csv" not in names


def test_knowledge_dtos_are_not_orm_models() -> None:
    from app.database.models import Base
    from app.schemas.knowledge import ChecklistItem, ProfessionProfile, StarExample

    for dto in (ChecklistItem, ProfessionProfile, StarExample):
        assert not issubclass(dto, Base)


def test_summary_dto_is_not_orm_model() -> None:
    from app.database.models import Base
    from app.schemas.session_summary import InterviewSummary, StarStatistics

    for dto in (InterviewSummary, StarStatistics):
        assert not issubclass(dto, Base)
