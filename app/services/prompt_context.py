import re

from app.schemas.answer import AnswerAnalysis
from app.schemas.knowledge import KnowledgeItem, StarExample
from app.schemas.question import InterviewQuestion
from app.schemas.vacancy import VacancyAnalysis
from app.services.session_statistics import AnsweredQuestion, SessionStatistics

NOT_SPECIFIED = "не указано"
CONTEXT_TAGS = (
    "vacancy_analysis",
    "knowledge_base",
    "interview_questions",
    "interview_question",
    "candidate_answers",
    "candidate_answer",
    "answer_analyses",
    "session_statistics",
    "star_examples",
)
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


def format_star_examples_context(examples: list[StarExample]) -> str:
    return "\n\n".join(
        "\n".join(
            [
                f"Пример {index}",
                f"Вопрос: {example.question}",
                f"Situation: {example.situation}",
                f"Task: {example.task}",
                f"Action: {example.action}",
                f"Result: {example.result}",
            ]
        )
        for index, example in enumerate(examples, start=1)
    )


def build_answer_context(
    question: InterviewQuestion,
    answer: str,
    analysis: VacancyAnalysis,
    star_examples: list[StarExample] | None = None,
) -> str:
    context = (
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
    if star_examples:
        context += (
            "\n\n<star_examples>\n"
            f"{neutralize_context_tags(format_star_examples_context(star_examples))}\n"
            "</star_examples>"
        )
    return context


def build_questions_context(analysis: VacancyAnalysis, items: list[KnowledgeItem]) -> str:
    return (
        "<vacancy_analysis>\n"
        f"{neutralize_context_tags(format_vacancy_context(analysis))}\n"
        "</vacancy_analysis>\n\n"
        "<knowledge_base>\n"
        f"{neutralize_context_tags(format_knowledge_context(items))}\n"
        "</knowledge_base>"
    )


def format_statistics_context(statistics: SessionStatistics) -> str:
    average = statistics.average_score if statistics.average_score is not None else "null"
    lines = [
        f"position: {statistics.position or NOT_SPECIFIED}",
        f"answered_questions: {statistics.answered_questions}",
        f"total_questions: {statistics.total_questions}",
        f"average_score: {average}",
    ]
    star = statistics.star_statistics
    if star is None:
        lines.append("star_statistics: null")
    else:
        lines.append(
            f"star_statistics: answers={star.answers}, situation={star.situation}, "
            f"task={star.task}, action={star.action}, result={star.result}"
        )
    return "\n".join(lines)


def format_analysis_context(analysis: AnswerAnalysis) -> str:
    star = analysis.star
    return "\n".join(
        [
            f"Оценка: {analysis.score}/10",
            f"Тип вопроса: {analysis.question_type.value}",
            f"STAR: situation={star.situation.value}, task={star.task.value}, "
            f"action={star.action.value}, result={star.result.value}",
            f"Сильные стороны:\n{_format_list(analysis.strengths)}",
            f"Слабые стороны:\n{_format_list(analysis.weaknesses)}",
            f"Рекомендации:\n{_format_list(analysis.recommendations)}",
        ]
    )


def _numbered_blocks(answered: list[AnsweredQuestion], render) -> str:
    return "\n\n".join(
        f"[{item.question.id}]\n{neutralize_context_tags(render(item))}" for item in answered
    )


def build_summary_context(
    analysis: VacancyAnalysis,
    answered: list[AnsweredQuestion],
    statistics: SessionStatistics,
) -> str:
    return (
        "<vacancy_analysis>\n"
        f"{neutralize_context_tags(format_vacancy_context(analysis))}\n"
        "</vacancy_analysis>\n\n"
        "<session_statistics>\n"
        f"{neutralize_context_tags(format_statistics_context(statistics))}\n"
        "</session_statistics>\n\n"
        "<interview_questions>\n"
        f"{_numbered_blocks(answered, lambda item: format_question_context(item.question))}\n"
        "</interview_questions>\n\n"
        "<candidate_answers>\n"
        f"{_numbered_blocks(answered, lambda item: item.answer)}\n"
        "</candidate_answers>\n\n"
        "<answer_analyses>\n"
        f"{_numbered_blocks(answered, lambda item: format_analysis_context(item.analysis))}\n"
        "</answer_analyses>"
    )
