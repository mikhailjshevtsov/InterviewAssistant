from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import MenuAction, MenuCallback


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🎯 Подготовка по вакансии",
        callback_data=MenuCallback(action=MenuAction.PREPARE),
    )
    builder.button(
        text="ℹ️ Помощь",
        callback_data=MenuCallback(action=MenuAction.HELP),
    )
    builder.adjust(1)
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🏠 Главное меню",
        callback_data=MenuCallback(action=MenuAction.MAIN_MENU),
    )
    return builder.as_markup()
