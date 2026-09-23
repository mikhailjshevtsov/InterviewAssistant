# Interview AI Assistant MVP

Telegram AI-assistant for interview preparation.

## Stack
- Python 3.12+
- aiogram 3.x
- OpenAI API
- SQLite
- CSV Knowledge Base

## Current stage
Stage 8: knowledge base and documentation.

The bot analyzes a vacancy, generates interview questions grounded in the CSV knowledge base, analyzes answers (score, STAR, recommendations, improved answer), builds a session summary and shows interview checklists. All OpenAI calls use the Responses API with Structured Outputs (Pydantic). Data is stored in `data/app.db`.

## Run
1. Create `.env` from `.env.example`
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `python -m app.main`

## Tests
`python -m pytest` — tests use a temporary SQLite database, never `data/app.db`, and never call the real OpenAI API.

`python -m pytest -m integration` — real OpenAI API tests; skipped when `OPENAI_API_KEY` is not set.

# Knowledge Base

The knowledge base is a set of UTF-8 CSV files in `knowledge_base/`. It can be edited without changing Python code; restart the bot to apply changes.

| File | Content | Used by |
|---|---|---|
| `professions.csv` | profession codes, display titles, aliases used to recognize vacancy titles | profession matching, checklist titles, validation |
| `questions.csv` | typical interview questions for analyst, manager, creative and technical professions (technical, behavioral, situational, experience) | question generation (`<knowledge_base>` prompt block) |
| `star_examples.csv` | fictional STAR answer examples | answer analysis for STAR questions (`<star_examples>` prompt block, structural reference only) |
| `checklists.csv` | checklist items: before the interview, what to bring, appearance, final check, during, end, after | «📋 Чек-листы» in Telegram, no OpenAI call |

Data flow: `CSV → CsvKnowledgeRepository → KnowledgeService / ChecklistService → QuestionService / AnswerService / Telegram handler`. Relevant rows are selected deterministically by profession, category and keywords; no vector database or embeddings. A missing or broken file does not stop the bot: the related feature continues without that data.

Validate the knowledge base after editing:

```powershell
python -m app.knowledge.validate
```

Documentation:
- [docs/KNOWLEDGE_BASE_GUIDE.md](docs/KNOWLEDGE_BASE_GUIDE.md) — file formats, columns, allowed values, filling rules, Google Sheets transfer, "UX Researcher" example;
- [docs/ADAPTATION_GUIDE.md](docs/ADAPTATION_GUIDE.md) — how to adapt the assistant to a new profession;
- [docs/PROMPTS.md](docs/PROMPTS.md) — prompts, inputs, outputs, Pydantic models, untrusted-data rules;
- [docs/USER_SCENARIOS.md](docs/USER_SCENARIOS.md) — user scenarios UC-01…UC-09;
- [docs/API_CONTRACTS.md](docs/API_CONTRACTS.md) — service contracts and Telegram callbacks.
