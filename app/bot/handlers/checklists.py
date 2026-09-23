from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import ChecklistCallback, MenuAction, MenuCallback
from app.bot.formatters import CHECKLISTS_EMPTY_TEXT, CHECKLISTS_MENU_TEXT, format_checklist
from app.bot.keyboards import (
    back_to_menu_keyboard,
    checklist_categories_keyboard,
    checklist_keyboard,
)
from app.services.checklist_service import ChecklistService

router = Router(name="checklists")


@router.callback_query(MenuCallback.filter(F.action == MenuAction.CHECKLISTS))
async def checklists_callback(callback: CallbackQuery, checklist_service: ChecklistService) -> None:
    categories = await checklist_service.list_categories()
    if isinstance(callback.message, Message):
        if categories:
            await callback.message.edit_text(
                CHECKLISTS_MENU_TEXT, reply_markup=checklist_categories_keyboard(categories)
            )
        else:
            await callback.message.edit_text(
                CHECKLISTS_EMPTY_TEXT, reply_markup=back_to_menu_keyboard()
            )
    await callback.answer()


@router.callback_query(ChecklistCallback.filter())
async def checklist_category_callback(
    callback: CallbackQuery,
    callback_data: ChecklistCallback,
    checklist_service: ChecklistService,
) -> None:
    items = await checklist_service.get_items(callback_data.category)
    titles = await checklist_service.profession_titles()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            format_checklist(callback_data.category, items, titles),
            reply_markup=checklist_keyboard(),
        )
    await callback.answer()
