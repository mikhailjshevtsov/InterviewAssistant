from enum import StrEnum

from aiogram.filters.callback_data import CallbackData


class MenuAction(StrEnum):
    PREPARE = "prepare"
    HELP = "help"
    MAIN_MENU = "main"
    GENERATE_QUESTIONS = "generate_questions"
    BACK_QUESTIONS = "back_questions"
    NEXT_QUESTION = "next_question"
    RETRY_ANSWER = "retry_answer"


class MenuCallback(CallbackData, prefix="menu"):
    action: MenuAction


class QuestionCallback(CallbackData, prefix="question"):
    question_id: str
