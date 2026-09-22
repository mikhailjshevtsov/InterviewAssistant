from app.services.vacancy_validator import VacancyValidationError


class LLMServiceError(Exception):
    """LLM call failed; the message is safe to log but not meant for users."""


class InvalidVacancyTextError(Exception):
    def __init__(self, error: VacancyValidationError):
        super().__init__(f"Invalid vacancy text: {error}")
        self.error = error
