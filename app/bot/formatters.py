from app.schemas.question import (
    InterviewQuestion,
    QuestionCategory,
    QuestionDifficulty,
    QuestionSet,
)
from app.schemas.vacancy import VacancyAnalysis

TELEGRAM_MESSAGE_LIMIT = 4096
BUTTON_TEXT_LIMIT = 48
NOT_SPECIFIED = "не указано"

CATEGORY_LABELS = {
    QuestionCategory.TECHNICAL: "технический",
    QuestionCategory.BEHAVIORAL: "поведенческий",
    QuestionCategory.SITUATIONAL: "ситуационный",
    QuestionCategory.EXPERIENCE: "об опыте",
}
DIFFICULTY_LABELS = {
    QuestionDifficulty.EASY: "лёгкий",
    QuestionDifficulty.MEDIUM: "средний",
    QuestionDifficulty.HARD: "сложный",
}


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


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
    return _truncate("\n\n".join(sections), TELEGRAM_MESSAGE_LIMIT)


def format_question_set(question_set: QuestionSet) -> str:
    lines = [
        f"{index}. {question.question}"
        for index, question in enumerate(question_set.questions, start=1)
    ]
    text = "📝 Вопросы для подготовки\n\n" + "\n\n".join(lines)
    text += "\n\nВыберите вопрос, чтобы ответить на него."
    return _truncate(text, TELEGRAM_MESSAGE_LIMIT)


def question_button_text(index: int, question: InterviewQuestion) -> str:
    return _truncate(f"{index}. {question.question}", BUTTON_TEXT_LIMIT)


def format_selected_question(question: InterviewQuestion) -> str:
    details = (
        f"Тип: {CATEGORY_LABELS[question.category]}, "
        f"сложность: {DIFFICULTY_LABELS[question.difficulty]}"
    )
    parts = [f"❓ Вопрос {question.id}", question.question, details]
    if question.star_required:
        parts.append(
            "💡 Ответьте по методике STAR: ситуация, задача, действия, результат."
        )
    parts.append("✍️ Напишите ответ одним сообщением.")
    return _truncate("\n\n".join(parts), TELEGRAM_MESSAGE_LIMIT)
