import asyncio
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.knowledge.csv_repository import CsvKnowledgeRepository, KnowledgeBaseError
from app.schemas.knowledge import KnowledgeItem
from app.schemas.question import QuestionCategory

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITEMS = 20
PROFESSION_SCORE = 3
CATEGORY_SCORE = 2
KEYWORD_SCORE = 1

# Curated spellings of CSV profession codes as they appear in vacancy titles.
PROFESSION_ALIASES: dict[str, tuple[str, ...]] = {
    "analyst": ("analyst", "аналитик"),
}

_WORD_RE = re.compile(r"[\w#+.]+")


@dataclass(frozen=True, slots=True)
class _ScoredItem:
    score: int
    item: KnowledgeItem


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


class KnowledgeService:
    def __init__(
        self,
        repository: CsvKnowledgeRepository | None = None,
        max_items: int = DEFAULT_MAX_ITEMS,
    ):
        self.repository = repository or CsvKnowledgeRepository()
        self.max_items = max_items
        self._items: list[KnowledgeItem] | None = None

    async def find_relevant(
        self,
        profession: str | None,
        categories: list[QuestionCategory],
        keywords: list[str],
    ) -> list[KnowledgeItem]:
        items = await self._get_items()
        wanted_categories = set(categories)
        phrases = {_normalize(keyword) for keyword in keywords if keyword.strip()}
        words = {word for phrase in phrases for word in _WORD_RE.findall(phrase)}

        scored: list[_ScoredItem] = []
        for item in items:
            profession_match = self._matches_profession(item.profession, profession)
            keyword_matches = self._count_keyword_matches(item, phrases, words)
            if not profession_match and not keyword_matches:
                continue
            score = (
                PROFESSION_SCORE * profession_match
                + CATEGORY_SCORE * (item.category in wanted_categories)
                + KEYWORD_SCORE * keyword_matches
            )
            scored.append(_ScoredItem(score, item))

        scored.sort(key=lambda entry: -entry.score)
        result = self._deduplicate(entry.item for entry in scored)[: self.max_items]
        if not result:
            logger.info("No relevant knowledge items found")
        return result

    async def _get_items(self) -> list[KnowledgeItem]:
        if self._items is None:
            try:
                self._items = await asyncio.to_thread(self.repository.load_questions)
            except KnowledgeBaseError:
                logger.exception("Knowledge base is unavailable; continuing without it")
                return []
            logger.info("Knowledge base loaded: %s items", len(self._items))
        return self._items

    @staticmethod
    def _matches_profession(item_profession: str, profession: str | None) -> bool:
        if not profession:
            return False
        title = _normalize(profession)
        aliases = PROFESSION_ALIASES.get(item_profession, (item_profession,))
        return any(alias in title for alias in aliases)

    @staticmethod
    def _count_keyword_matches(item: KnowledgeItem, phrases: set[str], words: set[str]) -> int:
        matches = 0
        for keyword in {_normalize(keyword) for keyword in item.keywords}:
            if " " in keyword:
                matched = any(keyword in phrase for phrase in phrases)
            else:
                matched = keyword in words
            matches += matched
        return matches

    @staticmethod
    def _deduplicate(items: Iterable[KnowledgeItem]) -> list[KnowledgeItem]:
        seen_ids: set[str] = set()
        seen_questions: set[str] = set()
        unique: list[KnowledgeItem] = []
        for item in items:
            question_key = _normalize(item.question)
            if item.id in seen_ids or question_key in seen_questions:
                continue
            seen_ids.add(item.id)
            seen_questions.add(question_key)
            unique.append(item)
        return unique
