import asyncio
import logging

from app.knowledge.csv_repository import CsvKnowledgeRepository, KnowledgeBaseError
from app.schemas.knowledge import (
    GENERAL_PROFESSION,
    ChecklistCategory,
    ChecklistItem,
    ChecklistPriority,
)

logger = logging.getLogger(__name__)

PRIORITY_ORDER = {priority: index for index, priority in enumerate(ChecklistPriority)}


class ChecklistService:
    """Interview checklists from knowledge_base/checklists.csv; read-only, no user state."""

    def __init__(self, repository: CsvKnowledgeRepository | None = None):
        self.repository = repository or CsvKnowledgeRepository()
        self._items: list[ChecklistItem] | None = None
        self._titles: dict[str, str] | None = None

    async def profession_titles(self) -> dict[str, str]:
        """Display names of profession codes from professions.csv."""
        if self._titles is None:
            try:
                profiles = await asyncio.to_thread(self.repository.load_professions)
            except KnowledgeBaseError:
                logger.warning("professions.csv is unavailable; showing profession codes")
                profiles = []
            self._titles = {profile.profession: profile.title for profile in profiles}
        return self._titles

    async def list_categories(self) -> list[ChecklistCategory]:
        present = {item.category for item in await self._get_items()}
        return [category for category in ChecklistCategory if category in present]

    async def get_items(self, category: ChecklistCategory) -> list[ChecklistItem]:
        """General items first, then profession-specific ones; each group by priority."""
        items = [item for item in await self._get_items() if item.category == category]
        return sorted(
            items,
            key=lambda item: (
                item.profession != GENERAL_PROFESSION,
                PRIORITY_ORDER[item.priority],
            ),
        )

    async def _get_items(self) -> list[ChecklistItem]:
        if self._items is None:
            try:
                self._items = await asyncio.to_thread(self.repository.load_checklists)
            except KnowledgeBaseError:
                logger.exception("Checklists are unavailable; continuing without them")
                return []
            logger.info("Checklists loaded: %s items", len(self._items))
        return self._items
