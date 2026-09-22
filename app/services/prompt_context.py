from app.schemas.knowledge import KnowledgeItem
from app.schemas.vacancy import VacancyAnalysis

NOT_SPECIFIED = "не указано"


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


def build_questions_context(analysis: VacancyAnalysis, items: list[KnowledgeItem]) -> str:
    return (
        "<vacancy_analysis>\n"
        f"{format_vacancy_context(analysis)}\n"
        "</vacancy_analysis>\n\n"
        "<knowledge_base>\n"
        f"{format_knowledge_context(items)}\n"
        "</knowledge_base>"
    )
