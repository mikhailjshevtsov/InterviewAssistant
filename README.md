# Interview AI Assistant MVP

Telegram ИИ-ассистент для подготовки к собеседованиям.

## Стек

- Python 3.12+
- aiogram 3.x
- OpenAI API
- SQLite
- CSV Knowledge Base

## Текущий этап

Stage 10: Persistent Interview Sessions — восстановление незавершённой сессии пользователя после перезапуска бота. Сессия продолжается с места разрыва соединения.

Бот анализирует вакансию, формирует вопросы с опорой на CSV-базу знаний, разбирает ответы (оценка, STAR, рекомендации, улучшенный ответ), строит итог сессии и показывает чек-листы подготовки. Все вызовы OpenAI идут через Responses API со Structured Outputs (Pydantic). Данные хранятся в `data/app.db`. Состояние интервью берётся из SQLite; FSM в памяти только для текущего диалога. После `/start` бот предлагает продолжить последнюю сессию, если она есть.

## Запуск

1. Создайте `.env` по образцу `.env.example`
2. Установите зависимости: `pip install -r requirements.txt`
3. Запустите: `python -m app.main`

## Тесты
`python -m pytest` — тесты используют временную базу SQLite, не трогают `data/app.db` и не вызывают реальный OpenAI API.

`python -m pytest -m integration` — тесты с реальным OpenAI API; пропускаются, если не задан `OPENAI_API_KEY`.

# База знаний

База знаний — набор CSV-файлов в кодировке UTF-8 в каталоге `knowledge_base/`. Их можно редактировать без изменения Python-кода; чтобы применить изменения, перезапустите бота.

| Файл | Содержание | Где используется |
|---|---|---|
| `professions.csv` | коды профессий, отображаемые названия, псевдонимы для распознавания должностей в вакансиях | сопоставление профессии, названия в чек-листах, валидация |
| `questions.csv` | типовые вопросы собеседования для аналитиков, менеджеров, креативных и технических профессий (technical, behavioral, situational, experience) | генерация вопросов (блок `<knowledge_base>` в промпте) |
| `star_examples.csv` | вымышленные примеры ответов по STAR | анализ ответов на STAR-вопросы (блок `<star_examples>`, только образец структуры) |
| `checklists.csv` | пункты чек-листов: до интервью, что взять с собой, внешний вид, финальная проверка, во время, завершение, после | «📋 Чек-листы» в Telegram, без вызова OpenAI |

Поток данных: `CSV → CsvKnowledgeRepository → KnowledgeService / ChecklistService → QuestionService / AnswerService / Telegram handler`. Подходящие строки отбираются детерминированно по профессии, категории и ключевым словам; векторная база и embeddings не используются. Отсутствующий или повреждённый файл не останавливает бота: связанная функция продолжает работать без этих данных.

После правок проверьте базу знаний:

```powershell
python -m app.knowledge.validate
```

# Документация

- [docs/KNOWLEDGE_BASE_GUIDE.md](docs/KNOWLEDGE_BASE_GUIDE.md) — форматы файлов, колонки, допустимые значения, правила заполнения, перенос в Google Sheets, пример «UX Researcher»;
- [docs/ADAPTATION_GUIDE.md](docs/ADAPTATION_GUIDE.md) — как адаптировать ассистента под новую профессию;
- [docs/PROMPTS.md](docs/PROMPTS.md) — промпты, входы, выходы, модели Pydantic, правила для недоверенных данных;
- [docs/USER_SCENARIOS.md](docs/USER_SCENARIOS.md) — пользовательские сценарии UC-01…UC-10;
- [docs/API_CONTRACTS.md](docs/API_CONTRACTS.md) — контракты сервисов и Telegram callbacks.

# На дальнейшее развитие

•  resume upload;
•  PDF/DOCX;
•  mock interview;
•  voice;
•  RAG;
•  vector database;
•  Google Sheets;
•  web UI;
•  admin panel;
•  authentication;
•  i18n;
•  export;
•  checklist progress;
•  social login;
•  new professions;
•  new question generation logic.