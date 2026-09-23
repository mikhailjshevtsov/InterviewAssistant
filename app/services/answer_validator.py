from dataclasses import dataclass
from enum import StrEnum

MIN_ANSWER_LENGTH = 10
# Replies that carry no content to analyze regardless of their length.
NON_ANSWERS = frozenset(
    {
        "не знаю",
        "незнаю",
        "без понятия",
        "затрудняюсь ответить",
        "нет ответа",
        "пропустить",
        "пропуск",
        "i don't know",
        "i dont know",
        "no idea",
        "skip",
    }
)


class AnswerValidationError(StrEnum):
    EMPTY = "empty"
    TOO_SHORT = "too_short"


@dataclass(frozen=True, slots=True)
class AnswerValidationResult:
    text: str
    error: AnswerValidationError | None = None

    @property
    def is_valid(self) -> bool:
        return self.error is None


def validate_answer_text(text: str | None) -> AnswerValidationResult:
    normalized = (text or "").strip()
    if not normalized:
        return AnswerValidationResult(normalized, AnswerValidationError.EMPTY)
    comparable = " ".join(normalized.lower().rstrip(".!?…").split())
    if len(normalized) < MIN_ANSWER_LENGTH or comparable in NON_ANSWERS:
        return AnswerValidationResult(normalized, AnswerValidationError.TOO_SHORT)
    return AnswerValidationResult(normalized)
