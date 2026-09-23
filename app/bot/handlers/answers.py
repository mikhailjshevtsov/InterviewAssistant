from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import MenuAction, MenuCallback
from app.bot.formatters import format_answer_analysis, format_question_set, format_selected_question
from app.bot.handlers.questions import open_question
from app.bot.keyboards import (
    answer_result_keyboard,
    back_to_menu_keyboard,
    question_selected_keyboard,
    questions_keyboard,
)
from app.bot.states import InterviewState
from app.bot.texts import (
    ANALYZING_ANSWER_TEXT,
    ANSWER_EMPTY_TEXT,
    ANSWER_IN_PROGRESS_TEXT,
    ANSWER_LLM_ERROR_TEXT,
    ANSWER_TOO_SHORT_TEXT,
    DATABASE_ERROR_TEXT,
    LAST_QUESTION_TEXT,
    NEXT_ACTION_HINT_TEXT,
    QUESTION_NOT_FOUND_TEXT,
)
from app.database.exceptions import DatabaseError, EntityNotFoundError
from app.schemas.question import QuestionSet
from app.services.answer_service import AnswerService
from app.services.answer_validator import AnswerValidationError
from app.services.exceptions import InvalidAnswerTextError, LLMServiceError
from app.services.question_service import QuestionService

router = Router(name="answers")

ANSWER_VALIDATION_TEXTS = {
    AnswerValidationError.EMPTY: ANSWER_EMPTY_TEXT,
    AnswerValidationError.TOO_SHORT: ANSWER_TOO_SHORT_TEXT,
}


@router.message(InterviewState.WAITING_ANSWER)
async def answer_received(
    message: Message, state: FSMContext, answer_service: AnswerService
) -> None:
    try:
        answer_text = AnswerService.require_valid_answer(message.text)
    except InvalidAnswerTextError as exc:
        await message.answer(ANSWER_VALIDATION_TEXTS[exc.error])
        return
    data = await state.get_data()
    session_id, question_id = data.get("session_id"), data.get("question_id")
    if session_id is None or question_id is None:
        await state.set_state(InterviewState.MAIN_MENU)
        await message.answer(QUESTION_NOT_FOUND_TEXT, reply_markup=back_to_menu_keyboard())
        return

    await state.set_state(InterviewState.ANALYZING_ANSWER)
    await message.answer(ANALYZING_ANSWER_TEXT)
    try:
        analysis = await answer_service.analyze_for_session(
            session_id, question_id, answer_text
        )
    except InvalidAnswerTextError as exc:
        await _back_to_waiting(message, state, ANSWER_VALIDATION_TEXTS[exc.error])
        return
    except LLMServiceError:
        await _back_to_waiting(message, state, ANSWER_LLM_ERROR_TEXT)
        return
    except EntityNotFoundError:
        await state.set_state(InterviewState.QUESTIONS)
        await message.answer(QUESTION_NOT_FOUND_TEXT, reply_markup=question_selected_keyboard())
        return
    except DatabaseError:
        await _back_to_waiting(message, state, DATABASE_ERROR_TEXT)
        return
    except Exception:
        await state.set_state(InterviewState.WAITING_ANSWER)
        raise

    await state.set_state(InterviewState.ANSWER_RESULT)
    await message.answer(format_answer_analysis(analysis), reply_markup=answer_result_keyboard())
    await state.set_state(InterviewState.NEXT_ACTION)


async def _back_to_waiting(message: Message, state: FSMContext, text: str) -> None:
    await state.set_state(InterviewState.WAITING_ANSWER)
    await message.answer(text, reply_markup=question_selected_keyboard())


@router.message(InterviewState.ANALYZING_ANSWER)
async def analyzing_answer_message(message: Message) -> None:
    await message.answer(ANSWER_IN_PROGRESS_TEXT)


@router.message(InterviewState.NEXT_ACTION)
async def next_action_message(message: Message) -> None:
    await message.answer(NEXT_ACTION_HINT_TEXT, reply_markup=answer_result_keyboard())


@router.callback_query(MenuCallback.filter(F.action == MenuAction.NEXT_QUESTION))
async def next_question_callback(
    callback: CallbackQuery,
    state: FSMContext,
    question_service: QuestionService,
    answer_service: AnswerService,
) -> None:
    data = await state.get_data()
    session_id, question_id = data.get("session_id"), data.get("question_id")
    message = callback.message
    if session_id is None or question_id is None or not isinstance(message, Message):
        await callback.answer(QUESTION_NOT_FOUND_TEXT, show_alert=True)
        return
    await callback.answer()
    try:
        next_question = await question_service.get_next_question(session_id, question_id)
        if next_question is not None:
            await open_question(message, state, session_id, next_question, answer_service)
            return
        questions = await question_service.list_questions(session_id)
    except DatabaseError:
        await message.answer(DATABASE_ERROR_TEXT, reply_markup=answer_result_keyboard())
        return

    await state.set_state(InterviewState.QUESTIONS)
    if not questions:
        await message.answer(QUESTION_NOT_FOUND_TEXT, reply_markup=back_to_menu_keyboard())
        return
    question_set = QuestionSet(questions=questions)
    await message.answer(
        f"{LAST_QUESTION_TEXT}\n\n{format_question_set(question_set)}",
        reply_markup=questions_keyboard(questions),
    )


@router.callback_query(MenuCallback.filter(F.action == MenuAction.RETRY_ANSWER))
async def retry_answer_callback(
    callback: CallbackQuery, state: FSMContext, question_service: QuestionService
) -> None:
    data = await state.get_data()
    session_id, question_id = data.get("session_id"), data.get("question_id")
    message = callback.message
    if session_id is None or question_id is None or not isinstance(message, Message):
        await callback.answer(QUESTION_NOT_FOUND_TEXT, show_alert=True)
        return
    try:
        question = await question_service.get_question(session_id, question_id)
    except DatabaseError:
        await callback.answer(DATABASE_ERROR_TEXT, show_alert=True)
        return
    if question is None:
        await callback.answer(QUESTION_NOT_FOUND_TEXT, show_alert=True)
        return
    await callback.answer()
    await state.set_state(InterviewState.WAITING_ANSWER)
    await message.answer(
        format_selected_question(question), reply_markup=question_selected_keyboard()
    )
