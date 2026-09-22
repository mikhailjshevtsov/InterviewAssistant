from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import MenuAction, MenuCallback
from app.bot.keyboards import back_to_menu_keyboard, main_menu_keyboard
from app.bot.states import InterviewState

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
    "для собеседования.\n\n"
    "Команда /start — начать заново."
)


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = message.from_user
    if user is not None:
        await state.update_data(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
        )
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
