from enum import StrEnum

from aiogram.filters.callback_data import CallbackData


class MenuAction(StrEnum):
    PREPARE = "prepare"
    HELP = "help"
    MAIN_MENU = "main"
    GENERATE_QUESTIONS = "generate_questions"


class MenuCallback(CallbackData, prefix="menu"):
    action: MenuAction


class QuestionCallback(CallbackData, prefix="question"):
    question_id: str
