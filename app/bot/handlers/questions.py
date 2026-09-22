from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import MenuAction, MenuCallback, QuestionCallback
from app.bot.formatters import format_question_set, format_selected_question
from app.bot.keyboards import (
    back_to_menu_keyboard,
    question_selected_keyboard,
    questions_keyboard,
    vacancy_result_keyboard,
)
from app.bot.states import InterviewState
from app.bot.texts import (
    ANSWER_RECEIVED_TEXT,
    DATABASE_ERROR_TEXT,
    GENERATING_QUESTIONS_TEXT,
    QUESTION_NOT_FOUND_TEXT,
    QUESTIONS_IN_PROGRESS_TEXT,
    QUESTIONS_LLM_ERROR_TEXT,
    QUESTIONS_UNAVAILABLE_TEXT,
)
from app.database.exceptions import DatabaseError, EntityNotFoundError
from app.schemas.question import QuestionSet
from app.services.exceptions import LLMServiceError, QuestionGenerationError
from app.services.question_service import QuestionService

router = Router(name="questions")


@router.callback_query(MenuCallback.filter(F.action == MenuAction.GENERATE_QUESTIONS))
async def generate_questions_callback(
    callback: CallbackQuery, state: FSMContext, question_service: QuestionService
) -> None:
    if await state.get_state() == InterviewState.GENERATING_QUESTIONS.state:
        await callback.answer(QUESTIONS_IN_PROGRESS_TEXT)
        return
    session_id = (await state.get_data()).get("session_id")
    message = callback.message
    if session_id is None or not isinstance(message, Message):
        await callback.answer(QUESTIONS_UNAVAILABLE_TEXT, show_alert=True)
        return

    await state.set_state(InterviewState.GENERATING_QUESTIONS)
    await callback.answer()
    try:
        existing = await question_service.list_questions(session_id)
        if existing:
            question_set = QuestionSet(questions=existing)
        else:
            await message.answer(GENERATING_QUESTIONS_TEXT)
            question_set = await question_service.generate_for_session(session_id)
    except LLMServiceError:
        await _fail(message, state, QUESTIONS_LLM_ERROR_TEXT)
        return
    except (QuestionGenerationError, EntityNotFoundError):
        await state.set_state(InterviewState.MAIN_MENU)
        await message.answer(QUESTIONS_UNAVAILABLE_TEXT, reply_markup=back_to_menu_keyboard())
        return
    except DatabaseError:
        await _fail(message, state, DATABASE_ERROR_TEXT)
        return
    except Exception:
        await state.set_state(InterviewState.VACANCY_RESULT)
        raise

    await state.set_state(InterviewState.QUESTIONS)
    await message.answer(
        format_question_set(question_set),
        reply_markup=questions_keyboard(question_set.questions),
    )


async def _fail(message: Message, state: FSMContext, text: str) -> None:
    await state.set_state(InterviewState.VACANCY_RESULT)
    await message.answer(text, reply_markup=vacancy_result_keyboard())


@router.callback_query(QuestionCallback.filter())
async def question_selected_callback(
    callback: CallbackQuery,
    callback_data: QuestionCallback,
    state: FSMContext,
    question_service: QuestionService,
) -> None:
    session_id = (await state.get_data()).get("session_id")
    message = callback.message
    if session_id is None or not isinstance(message, Message):
        await callback.answer(QUESTION_NOT_FOUND_TEXT, show_alert=True)
        return
    try:
        question = await question_service.get_question(session_id, callback_data.question_id)
    except DatabaseError:
        await callback.answer(DATABASE_ERROR_TEXT, show_alert=True)
        return
    if question is None:
        await callback.answer(QUESTION_NOT_FOUND_TEXT, show_alert=True)
        return

    await state.update_data(question_id=question.id)
    await state.set_state(InterviewState.WAITING_ANSWER)
    await callback.answer()
    await message.answer(
        format_selected_question(question), reply_markup=question_selected_keyboard()
    )


@router.message(InterviewState.GENERATING_QUESTIONS)
async def generating_questions_message(message: Message) -> None:
    await message.answer(QUESTIONS_IN_PROGRESS_TEXT)


@router.message(InterviewState.WAITING_ANSWER)
async def answer_received(message: Message, state: FSMContext) -> None:
    await state.set_state(InterviewState.QUESTIONS)
    await message.answer(ANSWER_RECEIVED_TEXT, reply_markup=question_selected_keyboard())
