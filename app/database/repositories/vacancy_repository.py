from sqlalchemy.ext.asyncio import AsyncSession

from app.database.exceptions import EntityNotFoundError
from app.database.models import Vacancy


class VacancyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: int, text: str) -> Vacancy:
        vacancy = Vacancy(user_id=user_id, text=text)
        self.session.add(vacancy)
        await self.session.flush()
        return vacancy

    async def get_by_id(self, vacancy_id: int) -> Vacancy | None:
        return await self.session.get(Vacancy, vacancy_id)

    async def save_analysis(
        self,
        vacancy_id: int,
        position: str | None,
        analysis_json: str,
    ) -> Vacancy:
        vacancy = await self.get_by_id(vacancy_id)
        if vacancy is None:
            raise EntityNotFoundError(f"Vacancy {vacancy_id} not found")
        vacancy.position = position
        vacancy.analysis_json = analysis_json
        await self.session.flush()
        return vacancy
