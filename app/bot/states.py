from aiogram.fsm.state import State, StatesGroup


class InterviewState(StatesGroup):
    MAIN_MENU = State()
    WAITING_VACANCY = State()
    ANALYZING_VACANCY = State()
    VACANCY_RESULT = State()
    GENERATING_QUESTIONS = State()
    QUESTIONS = State()
    WAITING_ANSWER = State()
    ANALYZING_ANSWER = State()
    ANSWER_RESULT = State()
    NEXT_ACTION = State()
    GENERATING_SUMMARY = State()
    SUMMARY_RESULT = State()
