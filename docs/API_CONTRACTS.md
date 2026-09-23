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

## 5. KnowledgeService

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

## 6. Telegram callbacks
- `menu:generate_questions` — сформировать или показать вопросы текущей сессии.
- `question:{question_id}` — выбрать вопрос, FSM → WAITING_ANSWER (или сохранённый результат, FSM → NEXT_ACTION).
- Ответ текстом: WAITING_ANSWER → ANALYZING_ANSWER → ANSWER_RESULT → NEXT_ACTION; при ошибке LLM — обратно WAITING_ANSWER.
- `menu:next_question` — следующий вопрос, FSM → WAITING_ANSWER; после последнего — список, FSM → QUESTIONS.
- `menu:back_questions` — список вопросов, FSM → QUESTIONS.
- `menu:retry_answer` — ответить на текущий вопрос заново, FSM → WAITING_ANSWER.
- `menu:main_menu` — главное меню.

## 7. Telegram layer
Handlers orchestrate state transitions and call application services. Business logic must not be embedded in handlers.
