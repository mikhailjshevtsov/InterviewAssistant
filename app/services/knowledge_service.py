import asyncio
import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TypeVar

from app.knowledge.csv_repository import CsvKnowledgeRepository, KnowledgeBaseError
from app.schemas.knowledge import KnowledgeItem, StarExample
from app.schemas.question import QuestionCategory

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITEMS = 20
DEFAULT_MAX_STAR_EXAMPLES = 2
PROFESSION_SCORE = 3
CATEGORY_SCORE = 2
KEYWORD_SCORE = 1

# Built-in spellings of CSV profession codes as they appear in vacancy titles;
# knowledge_base/professions.csv adds to them.
PROFESSION_ALIASES: dict[str, tuple[str, ...]] = {
    "analyst": ("analyst", "аналитик"),
}

_WORD_RE = re.compile(r"[\w#+.]+")

RowT = TypeVar("RowT", KnowledgeItem, StarExample)


@dataclass(frozen=True, slots=True)
class _ScoredItem:
    score: int
    item: KnowledgeItem | StarExample


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
        self._cache: dict[str, list] = {}
        self._aliases: dict[str, tuple[str, ...]] | None = None

    async def find_relevant(
        self,
        profession: str | None,
        categories: list[QuestionCategory],
        keywords: list[str],
    ) -> list[KnowledgeItem]:
        items = await self._load("questions", self.repository.load_questions)
        result = await self._rank(items, profession, categories, keywords, self.max_items)
        if not result:
            logger.info("No relevant knowledge items found")
        return result

    async def find_star_examples(
        self,
        profession: str | None,
        categories: list[QuestionCategory],
        keywords: list[str],
        limit: int = DEFAULT_MAX_STAR_EXAMPLES,
    ) -> list[StarExample]:
        examples = await self._load("star examples", self.repository.load_star_examples)
        return await self._rank(examples, profession, categories, keywords, limit)

    async def _rank(
        self,
        items: list[RowT],
        profession: str | None,
        categories: list[QuestionCategory],
        keywords: list[str],
        limit: int,
    ) -> list[RowT]:
        aliases = await self._get_aliases()
        wanted_categories = set(categories)
        phrases = {_normalize(keyword) for keyword in keywords if keyword.strip()}
        words = {word for phrase in phrases for word in _WORD_RE.findall(phrase)}

        scored: list[_ScoredItem] = []
        for item in items:
            profession_match = self._matches_profession(aliases, item.profession, profession)
            keyword_matches = self._count_keyword_matches(item.keywords, phrases, words)
            if not profession_match and not keyword_matches:
                continue
            score = (
                PROFESSION_SCORE * profession_match
                + CATEGORY_SCORE * (item.category in wanted_categories)
                + KEYWORD_SCORE * keyword_matches
            )
            scored.append(_ScoredItem(score, item))

        scored.sort(key=lambda entry: -entry.score)
        return self._deduplicate(entry.item for entry in scored)[:limit]

    async def _load(self, name: str, loader: Callable[[], list]) -> list:
        if name not in self._cache:
            try:
                self._cache[name] = await asyncio.to_thread(loader)
            except KnowledgeBaseError:
                logger.exception("Knowledge base %s are unavailable; continuing without them", name)
                return []
            logger.info("Knowledge base %s loaded: %s items", name, len(self._cache[name]))
        return self._cache[name]

    async def _get_aliases(self) -> dict[str, tuple[str, ...]]:
        if self._aliases is None:
            aliases = {code: set(names) for code, names in PROFESSION_ALIASES.items()}
            try:
                profiles = await asyncio.to_thread(self.repository.load_professions)
            except KnowledgeBaseError:
                logger.warning("professions.csv is unavailable; using built-in profession aliases")
                profiles = []
            for profile in profiles:
                aliases.setdefault(profile.profession, set()).update(profile.aliases)
            self._aliases = {code: tuple(names) for code, names in aliases.items()}
        return self._aliases

    @staticmethod
    def _matches_profession(
        aliases: dict[str, tuple[str, ...]], item_profession: str, profession: str | None
    ) -> bool:
        if not profession:
            return False
        title = _normalize(profession)
        return any(alias in title for alias in aliases.get(item_profession, (item_profession,)))

    @staticmethod
    def _count_keyword_matches(keywords: list[str], phrases: set[str], words: set[str]) -> int:
        matches = 0
        for keyword in {_normalize(keyword) for keyword in keywords}:
            if " " in keyword:
                matched = any(keyword in phrase for phrase in phrases)
            else:
                matched = keyword in words
            matches += matched
        return matches

    @staticmethod
    def _deduplicate(items: Iterable[RowT]) -> list[RowT]:
        seen_ids: set[str] = set()
        seen_questions: set[str] = set()
        unique: list[RowT] = []
        for item in items:
            question_key = _normalize(item.question)
            if item.id in seen_ids or question_key in seen_questions:
                continue
            seen_ids.add(item.id)
            seen_questions.add(question_key)
            unique.append(item)
        return unique
