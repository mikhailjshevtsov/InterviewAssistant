import logging
from dataclasses import dataclass
from enum import StrEnum

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.exceptions import DatabaseError
from app.database.models import InterviewSessionStatus, SessionQuestion
from app.database.repositories.answer_repository import AnswerRepository
from app.database.repositories.question_repository import SessionQuestionRepository
from app.database.repositories.session_repository import InterviewSessionRepository
from app.database.repositories.vacancy_repository import VacancyRepository
from app.schemas.answer import AnswerAnalysis
from app.schemas.question import InterviewQuestion
from app.schemas.session_summary import InterviewSummary
from app.schemas.vacancy import VacancyAnalysis

logger = logging.getLogger(__name__)

ANSWER_SCREENS = {
    InterviewSessionStatus.ANSWER_RESULT,
    InterviewSessionStatus.NEXT_ACTION,
    InterviewSessionStatus.WAITING_ANSWER,
    InterviewSessionStatus.ANALYZING_ANSWER,
}


class RecoveryScreen(StrEnum):
    VACANCY_INPUT = "vacancy_input"
    VACANCY_RESULT = "vacancy_result"
    QUESTIONS = "questions"
    ANSWER_RESULT = "answer_result"
    SUMMARY_RESULT = "summary_result"


@dataclass(frozen=True, slots=True)
class SessionRecovery:
    user_id: int
    session_id: int
    vacancy_id: int
    screen: RecoveryScreen
    question_id: str | None
    vacancy_analysis: VacancyAnalysis | None
    questions: list[InterviewQuestion]
    question: InterviewQuestion | None
    answer_analysis: AnswerAnalysis | None
    summary: InterviewSummary | None


class SessionRecoveryService:
    """Rebuilds the Telegram screen from SQLite after MemoryStorage is lost."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def get_active_session_id(self, user_id: int) -> int | None:
        recovery = await self.build(user_id)
        return None if recovery is None else recovery.session_id

    async def build(self, user_id: int) -> SessionRecovery | None:
        async with self.session_factory() as session:
            try:
                interview = await InterviewSessionRepository(session).get_latest_by_user(
                    user_id
                )
                if interview is None:
                    return None
                vacancy = await VacancyRepository(session).get_by_id(interview.vacancy_id)
                questions = await SessionQuestionRepository(session).list_by_session(
                    interview.id
                )
                latest_answer = await AnswerRepository(session).get_latest_analyzed_in_session(
                    interview.id
                )
                latest_question = next(
                    (
                        row
                        for row in questions
                        if latest_answer is not None
                        and row.id == latest_answer.session_question_id
                    ),
                    None,
                )
            except SQLAlchemyError as exc:
                logger.exception("Failed to load session recovery user_id=%s", user_id)
                raise DatabaseError("Failed to load interview session") from exc

        if vacancy is None:
            logger.warning(
                "Active session has no vacancy (user_id=%s, session_id=%s)",
                user_id,
                interview.id,
            )
            return None

        vacancy_analysis = _parse_json(vacancy.analysis_json, VacancyAnalysis, "vacancy")
        question_dtos = [_to_question(row) for row in questions]
        answer_analysis = (
            _parse_json(latest_answer.ai_analysis, AnswerAnalysis, "answer")
            if latest_answer is not None
            else None
        )
        current = _to_question(latest_question) if latest_question is not None else None
        summary = _parse_json(interview.summary_json, InterviewSummary, "summary")
        try:
            status = InterviewSessionStatus(interview.status)
        except ValueError:
            status = InterviewSessionStatus.QUESTIONS
        screen = _choose_screen(
            status,
            vacancy_analysis,
            question_dtos,
            current,
            answer_analysis,
            summary,
        )
        if screen is None:
            logger.warning(
                "Active session cannot be restored (user_id=%s, session_id=%s, status=%s)",
                user_id,
                interview.id,
                interview.status,
            )
            return None

        logger.info(
            "Session recovery built (user_id=%s, session_id=%s, screen=%s)",
            user_id,
            interview.id,
            screen,
        )
        return SessionRecovery(
            user_id=user_id,
            session_id=interview.id,
            vacancy_id=vacancy.id,
            screen=screen,
            question_id=None if current is None else current.id,
            vacancy_analysis=vacancy_analysis,
            questions=question_dtos,
            question=current,
            answer_analysis=answer_analysis,
            summary=summary,
        )


def _choose_screen(
    status: InterviewSessionStatus,
    vacancy_analysis: VacancyAnalysis | None,
    questions: list[InterviewQuestion],
    question: InterviewQuestion | None,
    answer_analysis: AnswerAnalysis | None,
    summary: InterviewSummary | None,
) -> RecoveryScreen | None:
    if summary is not None and status is InterviewSessionStatus.SUMMARY_RESULT:
        return RecoveryScreen.SUMMARY_RESULT
    if questions:
        if status in ANSWER_SCREENS and question is not None and answer_analysis is not None:
            return RecoveryScreen.ANSWER_RESULT
        return RecoveryScreen.QUESTIONS
    if vacancy_analysis is not None:
        return RecoveryScreen.VACANCY_RESULT
    if status in {
        InterviewSessionStatus.ANALYZING_VACANCY,
        InterviewSessionStatus.WAITING_VACANCY,
    }:
        return RecoveryScreen.VACANCY_INPUT
    return None


def _to_question(row: SessionQuestion) -> InterviewQuestion:
    return InterviewQuestion(
        id=row.question_id,
        question=row.question,
        category=row.category,
        difficulty=row.difficulty,
        star_required=row.star_required,
    )


def _parse_json(raw: str | None, model, name: str):
    if not raw:
        return None
    try:
        return model.model_validate_json(raw)
    except ValidationError:
        logger.warning("Saved %s is invalid", name)
        return None
