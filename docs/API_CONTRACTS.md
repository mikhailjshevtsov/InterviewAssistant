# API и контракты MVP

## 1. Общие принципы
Внутренние сервисы взаимодействуют через Python-функции с типизированными входами/выходами. Telegram handler не вызывает OpenAI напрямую.

DTO описаны Pydantic-моделями в `app/schemas/` и не связаны с ORM-моделями из `app/database/models.py`. Лишние поля отклоняются (`additionalProperties: false`).

## 2. VacancyService

`analyze(vacancy_id: int) -> VacancyAnalysis`

Ответ:
- position: str | null
- company: str | null
- hard_skills: list[str]
- soft_skills: list[str]
- experience: list[str]
- responsibilities: list[str]
- interview_topics: list[str]

Ошибки:
- ValidationError
- LLMServiceError
- VacancyAnalysisError

## 3. QuestionService

`generate(vacancy_analysis: VacancyAnalysis, knowledge_items: list[KnowledgeItem]) -> QuestionSet`

`generate_for_session(session_id: int) -> QuestionSet` — берёт сохранённый VacancyAnalysis, подбирает KnowledgeItem, вызывает LLM один раз и сохраняет вопросы; если вопросы для сессии уже есть, возвращает их без вызова LLM.

`list_questions(session_id: int) -> list[InterviewQuestion]`, `get_question(session_id: int, question_id: str) -> InterviewQuestion | None`

Ошибки:
- LLMServiceError (включая дубли и небезопасные для callback id вопросов)
- QuestionGenerationError (нет анализа вакансии)
- DatabaseError

QuestionSet:
- questions: list[InterviewQuestion] (1..10)

InterviewQuestion:
- id: str
- question: str
- category: technical | behavioral | situational | experience
- difficulty: easy | medium | hard
- star_required: bool

## 4. AnswerService

`analyze(question: InterviewQuestion, answer: str, vacancy_analysis: VacancyAnalysis) -> AnswerAnalysis`

`analyze_for_session(session_id: int, question_id: str, answer: str) -> AnswerAnalysis` — проверяет ответ (пустой, тривиальный вроде «да» / «не знаю» или короче 10 символов — без вызова LLM), берёт сохранённые вопрос и VacancyAnalysis, вызывает LLM один раз вне транзакции, затем в одной транзакции сохраняет Answer (связь с `interview_questions.id`), анализ и статус сессии `answer_result`.

`get_saved_analysis(session_id: int, question_id: str) -> AnswerAnalysis | None` — последний сохранённый анализ; повторный анализ только по явному действию пользователя.

Конструктор: `AnswerService(llm, session_factory=None, knowledge_service: KnowledgeService | None = None)`. Если передан `knowledge_service` и вопрос требует STAR (`star_required=True`), сервис подбирает до 2 примеров через `KnowledgeService.find_star_examples(position, [question.category], [question, hard_skills, interview_topics])` и передаёт их в `OpenAIService.analyze_answer(..., star_examples)`. Примеры попадают в блок `<star_examples>` без идентификаторов и служат только образцом структуры. Нет примеров или файла — анализ идёт без блока.

Ошибки:
- InvalidAnswerTextError (empty | too_short)
- LLMServiceError
- EntityNotFoundError (нет вопроса или анализа вакансии)
- DatabaseError (с rollback)

AnswerAnalysis:
- score: int (1..10)
- question_type: technical | behavioral | situational | experience
- star: StarAnalysis
- strengths: list[str]
- weaknesses: list[str]
- recommendations: list[str]
- improved_answer: str | null

STAR:
- situation: found | missing | unclear
- task: found | missing | unclear
- action: found | missing | unclear
- result: found | missing | unclear

## 5. SessionSummaryService

`get_saved_summary(session_id: int) -> InterviewSummary | None` — сохранённый итог, если он соответствует текущим ответам; без вызова LLM.

`create_summary(session_id: int) -> InterviewSummary` — берёт уже сохранённые AnswerAnalysis (повторно ответы не анализирует; для вопроса с несколькими попытками — последняя), считает статистику в Python, вызывает LLM один раз вне транзакции и сохраняет итог в `interview_sessions.summary_json` (статус `SUMMARY_RESULT`). Сохранённый итог переиспользуется; новый ответ в сессии его сбрасывает.

Python рассчитывает: position, answered_questions, total_questions, average_score (среднее, округление до 0.1), star_statistics. Эти значения передаются модели в `<session_statistics>` и всегда перезаписывают значения из ответа модели. Модель формирует содержательную часть.

Ошибки:
- NoAnswersError (нет ни одного проанализированного ответа; LLM не вызывается)
- LLMServiceError
- EntityNotFoundError (нет сессии или анализа вакансии)
- DatabaseError (с rollback; ответы не затрагиваются)

InterviewSummary:
- position: str | null
- answered_questions: int (≥ 0, ≤ total_questions)
- total_questions: int (≥ 0)
- average_score: float | null (1..10; null, если ответов нет)
- star_statistics: StarStatistics | null (answers, situation, task, action, result — сколько ответов на STAR-вопросы содержат элемент)
- strong_sides, weak_sides, star_strengths, star_gaps, recommendations, priority_topics: list[str]
- overall_summary: str

## 6. KnowledgeService

`find_relevant(profession: str | None, categories: list[QuestionCategory], keywords: list[str]) -> list[KnowledgeItem]`

KnowledgeItem (строка `knowledge_base/questions.csv`):
- id: str
- profession: str
- category: technical | behavioral | situational | experience
- question: str
- difficulty: easy | medium | hard
- star_required: bool
- keywords: list[str]

На MVP используется CSV и детерминированный отбор: +3 за профессию, +2 за категорию, +1 за каждое совпавшее ключевое слово; запись попадает в выдачу только при совпадении профессии или ключевого слова; дубликаты удаляются, максимум 20 записей. Нет совпадений — `[]`. Vector database и embeddings не используются.

Профессия вакансии сопоставляется с кодом профессии через псевдонимы из `knowledge_base/professions.csv` (подстрока в названии позиции, без учёта регистра).

`find_star_examples(profession: str | None, categories: list[QuestionCategory], keywords: list[str], limit: int = 2) -> list[StarExample]` — тот же алгоритм отбора по `knowledge_base/star_examples.csv`.

StarExample:
- id, profession, question, situation, task, action, result: str (непустые)
- category: technical | behavioral | situational | experience
- keywords: list[str]

Если CSV-файл отсутствует или не читается, методы возвращают `[]` и пишут предупреждение в лог; бот продолжает работать.

## 7. ChecklistService

`list_categories() -> list[ChecklistCategory]` — категории, в которых есть пункты, в порядке показа.

`get_items(category: ChecklistCategory) -> list[ChecklistItem]` — сначала общие пункты (`profession=general`), затем профессиональные; внутри группы по приоритету high → medium → low.

`profession_titles() -> dict[str, str]` — отображаемые названия профессий из `professions.csv`.

ChecklistItem (строка `knowledge_base/checklists.csv`):
- id, profession, title, item: str
- category: before_interview | documents | appearance | final_check | during_interview | end_interview | after_interview
- priority: high | medium | low
- keywords: list[str]

Сервис только читает CSV; прогресс пользователя не хранится.

## 8. Telegram callbacks
- `menu:checklists` — список категорий чек-листов (FSM не меняется).
- `checklist:{category}` — пункты выбранной категории, кнопки «⬅️ К чек-листам» и «🏠 Главное меню».
- `menu:summary` — итоги подготовки: сохранённый итог или генерация (FSM → GENERATING_SUMMARY → SUMMARY_RESULT; при ошибке — возврат в предыдущее состояние).
- `menu:generate_questions` — сформировать или показать вопросы текущей сессии.
- `question:{question_id}` — выбрать вопрос, FSM → WAITING_ANSWER (или сохранённый результат, FSM → NEXT_ACTION).
- Ответ текстом: WAITING_ANSWER → ANALYZING_ANSWER → ANSWER_RESULT → NEXT_ACTION; при ошибке LLM — обратно WAITING_ANSWER.
- `menu:next_question` — следующий вопрос, FSM → WAITING_ANSWER; после последнего — список, FSM → QUESTIONS.
- `menu:back_questions` — список вопросов, FSM → QUESTIONS.
- `menu:retry_answer` — ответить на текущий вопрос заново, FSM → WAITING_ANSWER.
- `menu:main_menu` — главное меню.

## 9. Telegram layer
Handlers orchestrate state transitions and call application services. Business logic must not be embedded in handlers.
