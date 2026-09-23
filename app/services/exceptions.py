from app.services.answer_validator import AnswerValidationError
from app.services.vacancy_validator import VacancyValidationError


class LLMServiceError(Exception):
    """LLM call failed; the message is safe to log but not meant for users."""


class QuestionGenerationError(Exception):
    """Questions cannot be generated for the session (e.g. no vacancy analysis yet)."""


class NoAnswersError(Exception):
    """A session summary was requested before any answer was analyzed."""


class InvalidVacancyTextError(Exception):
    def __init__(self, error: VacancyValidationError):
        super().__init__(f"Invalid vacancy text: {error}")
        self.error = error


class InvalidAnswerTextError(Exception):
    def __init__(self, error: AnswerValidationError):
        super().__init__(f"Invalid answer text: {error}")
        self.error = error
