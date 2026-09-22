from dataclasses import dataclass
from enum import StrEnum

MIN_VACANCY_LENGTH = 100


class VacancyValidationError(StrEnum):
    EMPTY = "empty"
    TOO_SHORT = "too_short"


@dataclass(frozen=True, slots=True)
class VacancyValidationResult:
    text: str
    error: VacancyValidationError | None = None

    @property
    def is_valid(self) -> bool:
        return self.error is None


def validate_vacancy_text(text: str | None) -> VacancyValidationResult:
    normalized = (text or "").strip()
    if not normalized:
        return VacancyValidationResult(normalized, VacancyValidationError.EMPTY)
    if len(normalized) < MIN_VACANCY_LENGTH:
        return VacancyValidationResult(normalized, VacancyValidationError.TOO_SHORT)
    return VacancyValidationResult(normalized)
