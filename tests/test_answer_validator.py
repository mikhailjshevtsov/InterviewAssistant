import pytest

from app.services.answer_validator import AnswerValidationError, validate_answer_text


@pytest.mark.parametrize("text", [None, "", "   ", "\n\t"])
def test_empty_answer(text: str | None) -> None:
    assert validate_answer_text(text).error == AnswerValidationError.EMPTY


@pytest.mark.parametrize(
    "text", ["да", "нет", "Не знаю", "не знаю.", "без понятия!", "I don't know", "ок"]
)
def test_trivial_answer_is_too_short(text: str) -> None:
    assert validate_answer_text(text).error == AnswerValidationError.TOO_SHORT


@pytest.mark.parametrize(
    "text",
    [
        "Использую LEFT JOIN",
        "  Я собрал требования у трёх отделов и описал процесс в BPMN.  ",
        "SQL " * 1000,
    ],
)
def test_meaningful_answer_is_valid(text: str) -> None:
    result = validate_answer_text(text)

    assert result.error is None
    assert result.text == text.strip()
