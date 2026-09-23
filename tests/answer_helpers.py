from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models import InterviewSessionStatus
from app.database.repositories import SessionQuestionRepository, VacancyRepository
from app.schemas.answer import AnswerAnalysis, StarAnalysis, StarElementStatus
from app.schemas.question import InterviewQuestion
from app.schemas.vacancy import VacancyAnalysis
from app.services.interview_session_service import InterviewSessionService
from app.services.user_service import UserService
from app.services.vacancy_service import VacancyService

VACANCY_TEXT = "Ищем бизнес-аналитика: SQL, BPMN, REST API, сбор требований. " * 3
VACANCY_ANALYSIS = VacancyAnalysis(
    position="Бизнес-аналитик",
    company=None,
    hard_skills=["SQL", "BPMN"],
    interview_topics=["SQL"],
)
QUESTIONS = [
    InterviewQuestion(
        id="Q-01",
        question="Какие SQL JOIN вы знаете и когда их применяете?",
        category="technical",
        difficulty="medium",
    ),
    InterviewQuestion(
        id="Q-02",
        question="Расскажите о сложном согласовании требований.",
        category="behavioral",
        difficulty="medium",
        star_required=True,
    ),
    InterviewQuestion(
        id="Q-03",
        question="Как вы описываете процессы в BPMN?",
        category="technical",
        difficulty="easy",
    ),
]
ANSWER_TEXT = (
    "Я собрал требования у трёх отделов, описал процесс в BPMN "
    "и согласовал API. Сервис запустили в срок."
)
ANSWER_ANALYSIS = AnswerAnalysis(
    score=7,
    question_type="behavioral",
    star=StarAnalysis(
        situation=StarElementStatus.FOUND,
        task=StarElementStatus.UNCLEAR,
        action=StarElementStatus.FOUND,
        result=StarElementStatus.MISSING,
    ),
    strengths=["Конкретные действия"],
    weaknesses=["Нет измеримого результата"],
    recommendations=["Добавьте метрики результата"],
    improved_answer="Я собрал требования у трёх отделов... [укажите результат в цифрах]",
)


async def create_session_with_questions(
    session_factory: async_sessionmaker[AsyncSession],
    telegram_id: int = 1,
    analyzed: bool = True,
) -> int:
    user = await UserService(session_factory).get_or_create_user(telegram_id, None, None)
    vacancy = await VacancyService(session_factory).create(user.id, VACANCY_TEXT)
    interview_session = await InterviewSessionService(session_factory).create(
        user.id, vacancy.id, InterviewSessionStatus.QUESTIONS
    )
    async with session_factory() as session:
        if analyzed:
            await VacancyRepository(session).save_analysis(
                vacancy.id, VACANCY_ANALYSIS.position, VACANCY_ANALYSIS.model_dump_json()
            )
        repository = SessionQuestionRepository(session)
        for question in QUESTIONS:
            await repository.create(
                session_id=interview_session.id,
                question_id=question.id,
                question=question.question,
                category=question.category.value,
                difficulty=question.difficulty.value,
                star_required=question.star_required,
            )
        await session.commit()
    return interview_session.id
