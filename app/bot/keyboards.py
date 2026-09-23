from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import ChecklistCallback, MenuAction, MenuCallback, QuestionCallback
from app.bot.formatters import CHECKLIST_CATEGORY_LABELS, question_button_text
from app.schemas.knowledge import ChecklistCategory
from app.schemas.question import InterviewQuestion


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🎯 Подготовка по вакансии",
        callback_data=MenuCallback(action=MenuAction.PREPARE),
    )
    builder.button(
        text="📋 Чек-листы",
        callback_data=MenuCallback(action=MenuAction.CHECKLISTS),
    )
    builder.button(
        text="ℹ️ Помощь",
        callback_data=MenuCallback(action=MenuAction.HELP),
    )
    builder.adjust(1)
    return builder.as_markup()


def checklist_categories_keyboard(categories: list[ChecklistCategory]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(
            text=CHECKLIST_CATEGORY_LABELS[category],
            callback_data=ChecklistCallback(category=category),
        )
    builder.button(
        text="🏠 Главное меню",
        callback_data=MenuCallback(action=MenuAction.MAIN_MENU),
    )
    builder.adjust(1)
    return builder.as_markup()


def checklist_keyboard() -> InlineKeyboardMarkup:
    return _with_main_menu(("⬅️ К чек-листам", MenuAction.CHECKLISTS))


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🏠 Главное меню",
        callback_data=MenuCallback(action=MenuAction.MAIN_MENU),
    )
    return builder.as_markup()


def vacancy_result_keyboard() -> InlineKeyboardMarkup:
    return _with_main_menu(("🎯 Сформировать вопросы", MenuAction.GENERATE_QUESTIONS))


def question_selected_keyboard() -> InlineKeyboardMarkup:
    return _with_main_menu(("📋 К списку вопросов", MenuAction.BACK_QUESTIONS))


SUMMARY_BUTTON_TEXT = "📊 Итоги подготовки"


def answer_result_keyboard() -> InlineKeyboardMarkup:
    return _with_main_menu(
        ("➡️ Следующий вопрос", MenuAction.NEXT_QUESTION),
        ("🔁 Ответить заново", MenuAction.RETRY_ANSWER),
        ("📋 К списку вопросов", MenuAction.BACK_QUESTIONS),
        (SUMMARY_BUTTON_TEXT, MenuAction.SESSION_SUMMARY),
    )


def summary_result_keyboard() -> InlineKeyboardMarkup:
    return _with_main_menu(("📋 К вопросам", MenuAction.BACK_QUESTIONS))


def summary_retry_keyboard() -> InlineKeyboardMarkup:
    return _with_main_menu(
        ("🔄 Повторить", MenuAction.SESSION_SUMMARY),
        ("📋 К вопросам", MenuAction.BACK_QUESTIONS),
    )


def questions_keyboard(questions: list[InterviewQuestion]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, question in enumerate(questions, start=1):
        builder.button(
            text=question_button_text(index, question),
            callback_data=QuestionCallback(question_id=question.id),
        )
    builder.button(
        text=SUMMARY_BUTTON_TEXT,
        callback_data=MenuCallback(action=MenuAction.SESSION_SUMMARY),
    )
    builder.button(
        text="🏠 Главное меню",
        callback_data=MenuCallback(action=MenuAction.MAIN_MENU),
    )
    builder.adjust(1)
    return builder.as_markup()


def _with_main_menu(*buttons: tuple[str, MenuAction]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for text, action in buttons:
        builder.button(text=text, callback_data=MenuCallback(action=action))
    builder.button(
        text="🏠 Главное меню",
        callback_data=MenuCallback(action=MenuAction.MAIN_MENU),
    )
    builder.adjust(1)
    return builder.as_markup()
