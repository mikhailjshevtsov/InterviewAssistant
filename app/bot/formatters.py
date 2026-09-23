from app.schemas.answer import AnswerAnalysis, StarElementStatus
from app.schemas.knowledge import (
    GENERAL_PROFESSION,
    ChecklistCategory,
    ChecklistItem,
    ChecklistPriority,
)
from app.schemas.question import (
    InterviewQuestion,
    QuestionCategory,
    QuestionDifficulty,
    QuestionSet,
)
from app.schemas.session_summary import InterviewSummary, StarStatistics
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
STAR_STATUS_ICONS = {
    StarElementStatus.FOUND: "🟢",
    StarElementStatus.UNCLEAR: "🟡",
    StarElementStatus.MISSING: "🔴",
}
STAR_STATUS_LABELS = {
    StarElementStatus.FOUND: "есть",
    StarElementStatus.UNCLEAR: "недостаточно конкретно",
    StarElementStatus.MISSING: "отсутствует",
}
DIFFICULTY_LABELS = {
    QuestionDifficulty.EASY: "лёгкий",
    QuestionDifficulty.MEDIUM: "средний",
    QuestionDifficulty.HARD: "сложный",
}


CHECKLIST_CATEGORY_LABELS = {
    ChecklistCategory.BEFORE_INTERVIEW: "📝 До интервью",
    ChecklistCategory.DOCUMENTS: "🎒 Что взять с собой",
    ChecklistCategory.APPEARANCE: "👔 Внешний вид",
    ChecklistCategory.FINAL_CHECK: "✅ Проверка перед началом",
    ChecklistCategory.DURING_INTERVIEW: "💬 Во время интервью",
    ChecklistCategory.END_INTERVIEW: "🤝 Завершение интервью",
    ChecklistCategory.AFTER_INTERVIEW: "📬 После интервью",
}
CHECKLISTS_MENU_TEXT = "📋 Чек-листы подготовки\n\nВыберите этап интервью:"
CHECKLISTS_EMPTY_TEXT = "📋 Чек-листы пока недоступны. Попробуйте позже."


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


def format_answer_analysis(analysis: AnswerAnalysis) -> str:
    star = analysis.star
    star_lines = "\n".join(
        f"{STAR_STATUS_ICONS[status]} {name} — {STAR_STATUS_LABELS[status]}"
        for name, status in (
            ("Situation (ситуация)", star.situation),
            ("Task (задача)", star.task),
            ("Action (действия)", star.action),
            ("Result (результат)", star.result),
        )
    )
    sections = [f"📊 Оценка: {analysis.score}/10", f"⭐ STAR-анализ\n{star_lines}"]
    for title, items in (
        ("💪 Сильные стороны", analysis.strengths),
        ("⚠️ Что улучшить", analysis.weaknesses),
        ("💡 Рекомендации", analysis.recommendations),
    ):
        if items:
            sections.append(title + "\n" + "\n".join(f"• {item}" for item in items))
    improved = analysis.improved_answer or (
        "Недостаточно данных для улучшенной версии — "
        "добавьте в ответ конкретику из своего опыта."
    )
    sections.append(f"✨ Улучшенный вариант\n{improved}")
    sections.append("➡️ Что дальше?")
    return _truncate("\n\n".join(sections), TELEGRAM_MESSAGE_LIMIT)


def format_saved_answer(question: InterviewQuestion, analysis: AnswerAnalysis) -> str:
    header = f"❓ Вопрос {question.id}\n\n{question.question}\n\n✅ Вы уже отвечали на этот вопрос."
    return _truncate(f"{header}\n\n{format_answer_analysis(analysis)}", TELEGRAM_MESSAGE_LIMIT)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"• {item}" for item in items)


def _star_statistics_lines(statistics: StarStatistics) -> str:
    lines = []
    for name, found in (
        ("Situation", statistics.situation),
        ("Task", statistics.task),
        ("Action", statistics.action),
        ("Result", statistics.result),
    ):
        if found == statistics.answers:
            icon = "🟢"
        elif found * 2 >= statistics.answers:
            icon = "🟡"
        else:
            icon = "🔴"
        lines.append(f"{icon} {name} — {found} из {statistics.answers}")
    return "\n".join(lines)


def format_session_summary(summary: InterviewSummary) -> str:
    average = (
        f"{summary.average_score:.1f}/10" if summary.average_score is not None else "нет оценок"
    )
    header = "🎯 Итоги подготовки"
    if summary.position:
        header += f"\n\n{summary.position}"
    sections = [
        header,
        "📊 Общий результат\n"
        f"Отвечено: {summary.answered_questions} из {summary.total_questions}\n"
        f"Средняя оценка: {average}",
    ]
    if summary.strong_sides:
        sections.append("💪 Сильные стороны\n" + _bullets(summary.strong_sides))
    if summary.weak_sides:
        sections.append("⚠️ Зоны для улучшения\n" + _bullets(summary.weak_sides))

    star_parts = []
    if summary.star_statistics is not None:
        star_parts.append(
            "Элемент раскрыт в ответах на STAR-вопросы:\n"
            + _star_statistics_lines(summary.star_statistics)
        )
    if summary.star_strengths:
        star_parts.append("Получается:\n" + _bullets(summary.star_strengths))
    if summary.star_gaps:
        star_parts.append("Требует внимания:\n" + _bullets(summary.star_gaps))
    if star_parts:
        sections.append("⭐ STAR\n" + "\n\n".join(star_parts))

    if summary.recommendations:
        sections.append("💡 Рекомендации\n" + _bullets(summary.recommendations))
    if summary.priority_topics:
        topics = "\n".join(
            f"{index}. {topic}" for index, topic in enumerate(summary.priority_topics, start=1)
        )
        sections.append(f"🔥 Что повторить в первую очередь\n{topics}")
    sections.append(f"📝 Общий вывод\n{summary.overall_summary}")
    return _truncate("\n\n".join(sections), TELEGRAM_MESSAGE_LIMIT)


def _checklist_entry(item: ChecklistItem, suffix: str = "") -> str:
    marker = "❗" if item.priority is ChecklistPriority.HIGH else "•"
    return f"{marker} {item.title}{suffix}\n{item.item}"


def format_checklist(
    category: ChecklistCategory,
    items: list[ChecklistItem],
    profession_titles: dict[str, str],
) -> str:
    general = [item for item in items if item.profession == GENERAL_PROFESSION]
    specific = [item for item in items if item.profession != GENERAL_PROFESSION]
    sections = [CHECKLIST_CATEGORY_LABELS[category]]
    sections.extend(_checklist_entry(item) for item in general)
    if specific:
        sections.append("🎯 Дополнительно для отдельных профессий")
        sections.extend(
            _checklist_entry(
                item, f" ({profession_titles.get(item.profession, item.profession)})"
            )
            for item in specific
        )
    if not items:
        sections.append("В этом разделе пока нет пунктов.")
    else:
        sections.append("❗ — сделать обязательно")
    return _truncate("\n\n".join(sections), TELEGRAM_MESSAGE_LIMIT)


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
