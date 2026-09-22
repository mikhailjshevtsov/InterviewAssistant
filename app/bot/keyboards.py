from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import MenuAction, MenuCallback, QuestionCallback
from app.bot.formatters import question_button_text
from app.schemas.question import InterviewQuestion


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


def vacancy_result_keyboard() -> InlineKeyboardMarkup:
    return _with_main_menu("🎯 Сформировать вопросы")


def question_selected_keyboard() -> InlineKeyboardMarkup:
    return _with_main_menu("📋 К списку вопросов")


def questions_keyboard(questions: list[InterviewQuestion]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, question in enumerate(questions, start=1):
        builder.button(
            text=question_button_text(index, question),
            callback_data=QuestionCallback(question_id=question.id),
        )
    builder.button(
        text="🏠 Главное меню",
        callback_data=MenuCallback(action=MenuAction.MAIN_MENU),
    )
    builder.adjust(1)
    return builder.as_markup()


def _with_main_menu(questions_button_text: str) -> InlineKeyboardMarkup:
    # Both buttons trigger GENERATE_QUESTIONS: it shows saved questions when they exist.
    builder = InlineKeyboardBuilder()
    builder.button(
        text=questions_button_text,
        callback_data=MenuCallback(action=MenuAction.GENERATE_QUESTIONS),
    )
    builder.button(
        text="🏠 Главное меню",
        callback_data=MenuCallback(action=MenuAction.MAIN_MENU),
    )
    builder.adjust(1)
    return builder.as_markup()
