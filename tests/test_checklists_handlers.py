from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, InlineKeyboardMarkup, Message

from app.bot.callbacks import ChecklistCallback, MenuAction, MenuCallback
from app.bot.formatters import (
    CHECKLIST_CATEGORY_LABELS,
    CHECKLISTS_EMPTY_TEXT,
    CHECKLISTS_MENU_TEXT,
    TELEGRAM_MESSAGE_LIMIT,
    format_checklist,
)
from app.bot.handlers.checklists import checklist_category_callback, checklists_callback
from app.bot.keyboards import main_menu_keyboard
from app.knowledge.csv_repository import CsvKnowledgeRepository
from app.schemas.knowledge import ChecklistCategory, ChecklistItem
from app.services.checklist_service import ChecklistService

CHECKLISTS = MenuCallback(action=MenuAction.CHECKLISTS).pack()
MAIN = MenuCallback(action=MenuAction.MAIN_MENU).pack()


@pytest.fixture
def edited(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    edit_text = AsyncMock()
    monkeypatch.setattr(Message, "edit_text", edit_text)
    return edit_text


def make_callback() -> SimpleNamespace:
    message = Message(
        message_id=1, date=datetime.now(UTC), chat=Chat(id=1, type="private"), text=None
    )
    return SimpleNamespace(message=message, answer=AsyncMock())


def callback_data_of(markup: InlineKeyboardMarkup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def item(item_id: str, profession: str, priority: str, title: str) -> ChecklistItem:
    return ChecklistItem(
        id=item_id,
        profession=profession,
        category=ChecklistCategory.DOCUMENTS,
        title=title,
        item=f"{title}: описание.",
        priority=priority,
    )


def test_main_menu_has_checklists_button() -> None:
    assert callback_data_of(main_menu_keyboard()) == [
        MenuCallback(action=MenuAction.PREPARE).pack(),
        CHECKLISTS,
        MenuCallback(action=MenuAction.HELP).pack(),
    ]


def test_checklist_callbacks_fit_telegram_limit() -> None:
    for category in ChecklistCategory:
        packed = ChecklistCallback(category=category).pack()
        assert len(packed.encode()) <= 64
        assert ChecklistCallback.unpack(packed).category is category


async def test_checklists_menu_lists_categories(edited: AsyncMock) -> None:
    callback = make_callback()

    await checklists_callback(callback, ChecklistService())

    text, markup = edited.await_args.args[0], edited.await_args.kwargs["reply_markup"]
    assert text == CHECKLISTS_MENU_TEXT
    assert callback_data_of(markup) == [
        *(ChecklistCallback(category=category).pack() for category in ChecklistCategory),
        MAIN,
    ]
    assert [row[0].text for row in markup.inline_keyboard][:-1] == [
        CHECKLIST_CATEGORY_LABELS[category] for category in ChecklistCategory
    ]
    callback.answer.assert_awaited_once()


async def test_checklists_menu_without_data(edited: AsyncMock, tmp_path: Path) -> None:
    service = ChecklistService(CsvKnowledgeRepository(tmp_path / "questions.csv"))

    await checklists_callback(make_callback(), service)

    assert edited.await_args.args[0] == CHECKLISTS_EMPTY_TEXT
    assert callback_data_of(edited.await_args.kwargs["reply_markup"]) == [MAIN]


@pytest.mark.parametrize("category", list(ChecklistCategory))
async def test_category_shows_items(edited: AsyncMock, category: ChecklistCategory) -> None:
    service = ChecklistService()
    callback = make_callback()

    await checklist_category_callback(callback, ChecklistCallback(category=category), service)

    text, markup = edited.await_args.args[0], edited.await_args.kwargs["reply_markup"]
    items = await service.get_items(category)
    assert text.startswith(CHECKLIST_CATEGORY_LABELS[category])
    assert all(entry.title in text for entry in items)
    assert len(text) <= TELEGRAM_MESSAGE_LIMIT
    assert "CL-" not in text
    assert callback_data_of(markup) == [CHECKLISTS, MAIN]
    callback.answer.assert_awaited_once()


def test_format_checklist_groups_profession_items() -> None:
    items = [
        item("C-1", "general", "high", "Паспорт"),
        item("C-2", "general", "low", "Ручка"),
        item("C-3", "analyst", "medium", "Портфолио"),
    ]

    text = format_checklist(ChecklistCategory.DOCUMENTS, items, {"analyst": "Аналитик"})

    assert text.index("❗ Паспорт") < text.index("• Ручка")
    assert text.index("• Ручка") < text.index("🎯 Дополнительно для отдельных профессий")
    assert "• Портфолио (Аналитик)" in text
    assert text.endswith("❗ — сделать обязательно")


def test_format_empty_checklist() -> None:
    text = format_checklist(ChecklistCategory.DOCUMENTS, [], {})

    assert text.endswith("В этом разделе пока нет пунктов.")
    assert "❗ — сделать обязательно" not in text
