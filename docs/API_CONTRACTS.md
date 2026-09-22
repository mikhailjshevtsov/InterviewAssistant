# API и контракты MVP

## 1. Общие принципы
Внутренние сервисы взаимодействуют через Python-функции с типизированными входами/выходами. Telegram handler не вызывает OpenAI напрямую.

DTO описаны Pydantic-моделями в `app/schemas/` и не связаны с ORM-моделями из `app/database/models.py`. Лишние поля отклоняются (`additionalProperties: false`).

## 2. VacancyService

`analyze(vacancy_text: str) -> VacancyAnalysis`

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

`generate(vacancy_analysis: VacancyAnalysis, knowledge_items: list[InterviewQuestion]) -> QuestionSet`

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

`find_relevant(profession: str, categories: list[str], keywords: list[str]) -> list[QuestionKBItem]`

На MVP используется CSV. Vector database не требуется.

## 6. Telegram layer
Handlers orchestrate state transitions and call application services. Business logic must not be embedded in handlers.
