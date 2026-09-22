import pytest

from app.config import settings
from app.schemas.vacancy import VacancyAnalysis
from app.services.openai_service import OpenAIService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not settings.openai_api_key, reason="OPENAI_API_KEY is not set"),
]

VACANCY_TEXT = """
Компания «Ромашка» ищет бизнес-аналитика (Middle).

Обязанности:
- сбор и анализ требований от заказчиков;
- описание бизнес-процессов в BPMN;
- подготовка технических заданий для разработки.

Требования:
- опыт работы бизнес-аналитиком от 2 лет;
- уверенное знание SQL;
- понимание REST API;
- развитые коммуникативные навыки.
"""


async def test_real_vacancy_analysis() -> None:
    service = OpenAIService.from_settings()
    try:
        result = await service.analyze_vacancy(VACANCY_TEXT)
    finally:
        await service.close()

    assert isinstance(result, VacancyAnalysis)
    assert result.position
    assert any("sql" in skill.lower() for skill in result.hard_skills)
    assert result.responsibilities
