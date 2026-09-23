from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import MenuAction, MenuCallback
from app.bot.keyboards import back_to_menu_keyboard, main_menu_keyboard
from app.bot.states import InterviewState
from app.bot.texts import DATABASE_ERROR_TEXT
from app.database.exceptions import DatabaseError
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
    "Команда /start — начать заново."
)


@router.message(CommandStart())
async def start_handler(
    message: Message, state: FSMContext, user_service: UserService
) -> None:
    await state.clear()
    telegram_user = message.from_user
    if telegram_user is not None:
        try:
            user = await user_service.get_or_create_user(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                full_name=telegram_user.full_name,
            )
        except DatabaseError:
            await message.answer(DATABASE_ERROR_TEXT)
            return
        await state.update_data(user_id=user.id)
    await state.set_state(InterviewState.MAIN_MENU)
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())


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
