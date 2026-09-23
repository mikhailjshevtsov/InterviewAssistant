import re

from app.schemas.knowledge import KnowledgeItem
from app.schemas.question import InterviewQuestion
from app.schemas.vacancy import VacancyAnalysis

NOT_SPECIFIED = "не указано"
CONTEXT_TAGS = ("vacancy_analysis", "knowledge_base", "interview_question", "candidate_answer")
_CONTEXT_TAG_RE = re.compile(rf"<\s*/?\s*({'|'.join(CONTEXT_TAGS)})\s*>", re.IGNORECASE)


def neutralize_context_tags(text: str) -> str:
    """Stops untrusted text from closing or opening a context block."""
    return _CONTEXT_TAG_RE.sub(lambda match: f"[{match.group(1)}]", text)


def _format_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else NOT_SPECIFIED


def format_vacancy_context(analysis: VacancyAnalysis) -> str:
    return "\n\n".join(
        [
            f"Позиция:\n{analysis.position or NOT_SPECIFIED}",
            f"Компания:\n{analysis.company or NOT_SPECIFIED}",
            f"Hard skills:\n{_format_list(analysis.hard_skills)}",
            f"Soft skills:\n{_format_list(analysis.soft_skills)}",
            f"Опыт:\n{_format_list(analysis.experience)}",
            f"Обязанности:\n{_format_list(analysis.responsibilities)}",
            f"Темы:\n{_format_list(analysis.interview_topics)}",
        ]
    )


def format_knowledge_context(items: list[KnowledgeItem]) -> str:
    if not items:
        return "Материалы не найдены."
    return "\n\n".join(
        "\n".join(
            [
                f"[KB-{item.id}]",
                f"Категория: {item.category.value}",
                f"Профессия: {item.profession}",
                f"Вопрос: {item.question}",
                f"Сложность: {item.difficulty.value}",
                f"STAR: {'да' if item.star_required else 'нет'}",
                f"Ключевые слова: {', '.join(item.keywords) or NOT_SPECIFIED}",
            ]
        )
        for item in items
    )


def format_question_context(question: InterviewQuestion) -> str:
    return "\n".join(
        [
            f"Вопрос: {question.question}",
            f"Категория: {question.category.value}",
            f"Сложность: {question.difficulty.value}",
            f"Ожидается ответ по STAR: {'да' if question.star_required else 'нет'}",
        ]
    )


def build_answer_context(
    question: InterviewQuestion, answer: str, analysis: VacancyAnalysis
) -> str:
    return (
        "<vacancy_analysis>\n"
        f"{neutralize_context_tags(format_vacancy_context(analysis))}\n"
        "</vacancy_analysis>\n\n"
        "<interview_question>\n"
        f"{neutralize_context_tags(format_question_context(question))}\n"
        "</interview_question>\n\n"
        "<candidate_answer>\n"
        f"{neutralize_context_tags(answer)}\n"
        "</candidate_answer>"
    )


def build_questions_context(analysis: VacancyAnalysis, items: list[KnowledgeItem]) -> str:
    return (
        "<vacancy_analysis>\n"
        f"{format_vacancy_context(analysis)}\n"
        "</vacancy_analysis>\n\n"
        "<knowledge_base>\n"
        f"{format_knowledge_context(items)}\n"
        "</knowledge_base>"
    )
