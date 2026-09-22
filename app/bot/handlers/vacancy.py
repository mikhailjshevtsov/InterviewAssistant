from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import MenuAction, MenuCallback
from app.bot.keyboards import back_to_menu_keyboard
from app.bot.states import InterviewState
from app.services.vacancy_validator import (
    MIN_VACANCY_LENGTH,
    VacancyValidationError,
    validate_vacancy_text,
)

router = Router(name="vacancy")

VALIDATION_ERROR_TEXTS = {
    VacancyValidationError.EMPTY: (
        "📝 Пожалуйста, отправьте текст вакансии обычным сообщением. "
        "Файлы, фото и стикеры пока не поддерживаются."
    ),
    VacancyValidationError.TOO_SHORT: (
        "⚠️ Похоже, информации недостаточно. "
        f"Отправьте более подробный текст вакансии "
        f"(не короче {MIN_VACANCY_LENGTH} символов)."
    ),
}


@router.callback_query(MenuCallback.filter(F.action == MenuAction.PREPARE))
async def prepare_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(InterviewState.WAITING_VACANCY)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "📄 Отправьте текст вакансии.\n\n"
            "Для лучшего результата используйте полный текст: "
            "требования, обязанности, стек и условия.",
            reply_markup=back_to_menu_keyboard(),
        )
    await callback.answer()


@router.message(InterviewState.WAITING_VACANCY)
async def vacancy_received(message: Message, state: FSMContext) -> None:
    result = validate_vacancy_text(message.text)
    if result.error is not None:
        await message.answer(
            VALIDATION_ERROR_TEXTS[result.error],
            reply_markup=back_to_menu_keyboard(),
        )
        return

    await state.update_data(vacancy_text=result.text)
    await state.set_state(InterviewState.ANALYZING_VACANCY)
    await message.answer(
        "🔎 Вакансия получена. Анализ будет подключён на следующем этапе.",
        reply_markup=back_to_menu_keyboard(),
    )


@router.message(InterviewState.ANALYZING_VACANCY)
async def analyzing_vacancy_message(message: Message) -> None:
    await message.answer(
        "⏳ Вакансия уже получена. Анализ будет подключён на следующем этапе.\n"
        "Чтобы начать заново, вернитесь в главное меню.",
        reply_markup=back_to_menu_keyboard(),
    )
