from app.schemas.vacancy import VacancyAnalysis

TELEGRAM_MESSAGE_LIMIT = 4096
NOT_SPECIFIED = "не указано"


def _format_value(title: str, value: str | None) -> str:
    return f"{title}:\n{value or NOT_SPECIFIED}"


def _format_list(title: str, items: list[str]) -> str:
    lines = "\n".join(f"• {item}" for item in items) if items else NOT_SPECIFIED
    return f"{title}:\n{lines}"


def format_vacancy_analysis(analysis: VacancyAnalysis) -> str:
    sections = [
        "🎯 Анализ вакансии",
        _format_value("Позиция", analysis.position),
        _format_value("Компания", analysis.company),
        _format_list("Hard skills", analysis.hard_skills),
        _format_list("Soft skills", analysis.soft_skills),
        _format_list("Опыт", analysis.experience),
        _format_list("Обязанности", analysis.responsibilities),
        _format_list("Темы для подготовки", analysis.interview_topics),
    ]
    text = "\n\n".join(sections)
    if len(text) > TELEGRAM_MESSAGE_LIMIT:
        text = text[: TELEGRAM_MESSAGE_LIMIT - 1].rstrip() + "…"
    return text
