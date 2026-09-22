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
