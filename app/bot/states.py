from aiogram.fsm.state import State, StatesGroup


class InterviewState(StatesGroup):
    MAIN_MENU = State()
    WAITING_VACANCY = State()
    ANALYZING_VACANCY = State()
    # Declared for the next stages, not used yet.
    VACANCY_RESULT = State()
    QUESTIONS = State()
    WAITING_ANSWER = State()
    ANALYZING_ANSWER = State()
    ANSWER_RESULT = State()
    NEXT_ACTION = State()
