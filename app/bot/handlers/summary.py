from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import MenuAction, MenuCallback
from app.bot.formatters import format_session_summary
from app.bot.keyboards import (
    back_to_menu_keyboard,
    question_selected_keyboard,
    summary_result_keyboard,
    summary_retry_keyboard,
)
from app.bot.states import InterviewState
from app.bot.texts import (
    DATABASE_ERROR_TEXT,
    GENERATING_SUMMARY_TEXT,
    QUESTIONS_UNAVAILABLE_TEXT,
    SUMMARY_IN_PROGRESS_TEXT,
    SUMMARY_LLM_ERROR_TEXT,
    SUMMARY_NO_ANSWERS_TEXT,
    SUMMARY_RESULT_HINT_TEXT,
)
from app.database.exceptions import DatabaseError, EntityNotFoundError
from app.services.exceptions import LLMServiceError, NoAnswersError
from app.services.session_summary_service import SessionSummaryService

router = Router(name="summary")


@router.callback_query(MenuCallback.filter(F.action == MenuAction.SESSION_SUMMARY))
async def session_summary_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session_summary_service: SessionSummaryService,
) -> None:
    previous_state = await state.get_state()
    if previous_state == InterviewState.GENERATING_SUMMARY.state:
        await callback.answer(SUMMARY_IN_PROGRESS_TEXT)
        return
    session_id = (await state.get_data()).get("session_id")
    message = callback.message
    if session_id is None or not isinstance(message, Message):
        await callback.answer(QUESTIONS_UNAVAILABLE_TEXT, show_alert=True)
        return

    await state.set_state(InterviewState.GENERATING_SUMMARY)
    await callback.answer()
    try:
        summary = await session_summary_service.get_saved_summary(session_id)
        if summary is None:
            await message.answer(GENERATING_SUMMARY_TEXT)
            summary = await session_summary_service.create_summary(session_id)
    except NoAnswersError:
        await state.set_state(previous_state)
        await message.answer(SUMMARY_NO_ANSWERS_TEXT, reply_markup=question_selected_keyboard())
        return
    except LLMServiceError:
        await state.set_state(previous_state)
        await message.answer(SUMMARY_LLM_ERROR_TEXT, reply_markup=summary_retry_keyboard())
        return
    except EntityNotFoundError:
        await state.set_state(InterviewState.MAIN_MENU)
        await message.answer(QUESTIONS_UNAVAILABLE_TEXT, reply_markup=back_to_menu_keyboard())
        return
    except DatabaseError:
        await state.set_state(previous_state)
        await message.answer(DATABASE_ERROR_TEXT, reply_markup=summary_retry_keyboard())
        return
    except Exception:
        await state.set_state(previous_state)
        raise

    await state.set_state(InterviewState.SUMMARY_RESULT)
    await message.answer(format_session_summary(summary), reply_markup=summary_result_keyboard())


@router.message(InterviewState.GENERATING_SUMMARY)
async def generating_summary_message(message: Message) -> None:
    await message.answer(SUMMARY_IN_PROGRESS_TEXT)


@router.message(InterviewState.SUMMARY_RESULT)
async def summary_result_message(message: Message) -> None:
    await message.answer(SUMMARY_RESULT_HINT_TEXT, reply_markup=summary_result_keyboard())
