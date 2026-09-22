import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.bot.handlers.start import router as start_router
from app.bot.handlers.vacancy import router as vacancy_router
from app.database.database import AsyncSessionFactory, engine, init_db
from app.services.interview_session_service import InterviewSessionService
from app.services.openai_service import OpenAIService
from app.services.user_service import UserService
from app.services.vacancy_service import VacancyService

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


async def main() -> None:
    bot = Bot(token=settings.bot_token)
    await init_db()
    openai_service = OpenAIService.from_settings()

    dp = Dispatcher(
        storage=MemoryStorage(),
        user_service=UserService(AsyncSessionFactory),
        vacancy_service=VacancyService(AsyncSessionFactory, llm=openai_service),
        interview_session_service=InterviewSessionService(AsyncSessionFactory),
    )
    dp.include_routers(start_router, vacancy_router)

    try:
        await dp.start_polling(bot)
    finally:
        await openai_service.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
