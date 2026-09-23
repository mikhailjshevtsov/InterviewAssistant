from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import MenuAction, MenuCallback
from app.bot.formatters import (
    format_question_set,
    format_saved_answer,
    format_session_summary,
    format_vacancy_analysis,
)
from app.bot.keyboards import (
    answer_result_keyboard,
    back_to_menu_keyboard,
    continue_session_keyboard,
    main_menu_keyboard,
    questions_keyboard,
    summary_result_keyboard,
    vacancy_result_keyboard,
)
from app.bot.states import InterviewState
from app.bot.texts import (
    CONTINUE_SESSION_TEXT,
    DATABASE_ERROR_TEXT,
    RECOVERY_UNAVAILABLE_TEXT,
    VACANCY_PROMPT_TEXT,
)
from app.database.exceptions import DatabaseError
from app.schemas.question import QuestionSet
from app.services.session_recovery_service import RecoveryScreen, SessionRecovery, SessionRecoveryService
from app.services.user_service import UserService

router = Router(name="start")

WELCOME_TEXT = (
    "👋 Добро пожаловать!\n\n"
    "Я помогу подготовиться к собеседованию: "
    "проанализировать вакансию, сформировать вопросы "
    "и разобрать ваши ответы."
)

MAIN_MENU_TEXT = "🏠 Главное меню\n\nВыберите действие:"

HELP_TEXT = (
    "ℹ️ Помощь\n\n"
    "1. Нажмите «🎯 Подготовка по вакансии».\n"
    "2. Отправьте полный текст вакансии одним сообщением "
    "(не короче 100 символов).\n"
    "3. Бот проанализирует вакансию и подготовит вопросы "
    "для собеседования.\n"
    "4. Ответьте на вопросы и получите разбор и итоговый отчёт.\n\n"
    "«📋 Чек-листы» — что сделать до, во время и после интервью.\n\n"
    "Команда /start открывает меню. Если есть сохранённая подготовка, "
    "бот предложит продолжить её."
)

SCREEN_STATE = {
    RecoveryScreen.VACANCY_INPUT: InterviewState.WAITING_VACANCY,
    RecoveryScreen.VACANCY_RESULT: InterviewState.VACANCY_RESULT,
    RecoveryScreen.QUESTIONS: InterviewState.QUESTIONS,
    RecoveryScreen.ANSWER_RESULT: InterviewState.NEXT_ACTION,
    RecoveryScreen.SUMMARY_RESULT: InterviewState.SUMMARY_RESULT,
}


@router.message(CommandStart())
async def start_handler(
    message: Message,
    state: FSMContext,
    user_service: UserService,
    session_recovery_service: SessionRecoveryService,
) -> None:
    await state.clear()
    telegram_user = message.from_user
    if telegram_user is None:
        await state.set_state(InterviewState.MAIN_MENU)
        await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())
        return
    try:
        user = await user_service.get_or_create_user(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            full_name=telegram_user.full_name,
        )
        recovery = await session_recovery_service.build(user.id)
    except DatabaseError:
        await message.answer(DATABASE_ERROR_TEXT)
        return
    await state.update_data(user_id=user.id)
    if recovery is None:
        await state.set_state(InterviewState.MAIN_MENU)
        await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())
        return
    await state.set_state(InterviewState.MAIN_MENU)
    await message.answer(CONTINUE_SESSION_TEXT, reply_markup=continue_session_keyboard())


@router.callback_query(MenuCallback.filter(F.action == MenuAction.CONTINUE_SESSION))
async def continue_session_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session_recovery_service: SessionRecoveryService,
) -> None:
    user_id = (await state.get_data()).get("user_id")
    if user_id is None:
        await callback.answer(RECOVERY_UNAVAILABLE_TEXT, show_alert=True)
        return
    try:
        recovery = await session_recovery_service.build(user_id)
    except DatabaseError:
        await callback.answer(DATABASE_ERROR_TEXT, show_alert=True)
        return
    if recovery is None or not isinstance(callback.message, Message):
        await callback.answer(RECOVERY_UNAVAILABLE_TEXT, show_alert=True)
        return
    await _apply_recovery(state, recovery)
    await callback.answer()
    await callback.message.answer(*_recovery_message(recovery))


@router.callback_query(MenuCallback.filter(F.action == MenuAction.NEW_SESSION))
async def new_session_callback(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = (await state.get_data()).get("user_id")
    await state.clear()
    if user_id is not None:
        await state.update_data(user_id=user_id)
    await state.set_state(InterviewState.WAITING_VACANCY)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            VACANCY_PROMPT_TEXT, reply_markup=back_to_menu_keyboard()
        )
    await callback.answer()


@router.callback_query(MenuCallback.filter(F.action == MenuAction.MAIN_MENU))
async def main_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(InterviewState.MAIN_MENU)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            MAIN_MENU_TEXT, reply_markup=main_menu_keyboard()
        )
    await callback.answer()


@router.callback_query(MenuCallback.filter(F.action == MenuAction.HELP))
async def help_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(InterviewState.MAIN_MENU)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            HELP_TEXT, reply_markup=back_to_menu_keyboard()
        )
    await callback.answer()


async def _apply_recovery(state: FSMContext, recovery: SessionRecovery) -> None:
    await state.update_data(
        user_id=recovery.user_id,
        session_id=recovery.session_id,
        vacancy_id=recovery.vacancy_id,
        question_id=recovery.question_id,
    )
    await state.set_state(SCREEN_STATE[recovery.screen])


def _recovery_message(recovery: SessionRecovery) -> tuple[str, dict]:
    if recovery.screen is RecoveryScreen.VACANCY_INPUT:
        return VACANCY_PROMPT_TEXT, {"reply_markup": back_to_menu_keyboard()}
    if recovery.screen is RecoveryScreen.VACANCY_RESULT and recovery.vacancy_analysis:
        return format_vacancy_analysis(recovery.vacancy_analysis), {
            "reply_markup": vacancy_result_keyboard()
        }
    if recovery.screen is RecoveryScreen.QUESTIONS:
        question_set = QuestionSet(questions=recovery.questions)
        return format_question_set(question_set), {
            "reply_markup": questions_keyboard(recovery.questions)
        }
    if (
        recovery.screen is RecoveryScreen.ANSWER_RESULT
        and recovery.question is not None
        and recovery.answer_analysis is not None
    ):
        return format_saved_answer(recovery.question, recovery.answer_analysis), {
            "reply_markup": answer_result_keyboard()
        }
    if recovery.screen is RecoveryScreen.SUMMARY_RESULT and recovery.summary is not None:
        return format_session_summary(recovery.summary), {
            "reply_markup": summary_result_keyboard()
        }
    return RECOVERY_UNAVAILABLE_TEXT, {"reply_markup": back_to_menu_keyboard()}
