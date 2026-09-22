# Interview AI Assistant MVP

Telegram AI-assistant for interview preparation.

## Stack
- Python 3.12+
- aiogram 3.x
- OpenAI API
- SQLite
- CSV Knowledge Base

## Current stage
Stage 5: vacancy analysis and interview question generation via the OpenAI Responses API (Structured Outputs with Pydantic). Questions are grounded in `knowledge_base/questions.csv` using deterministic keyword/profession matching (no embeddings) and stored per interview session in `data/app.db`. Answer analysis is not implemented yet.

## Run
1. Create `.env` from `.env.example`
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `python -m app.main`

## Tests
`python -m pytest` — tests use a temporary SQLite database, never `data/app.db`, and never call the real OpenAI API.

`python -m pytest -m integration` — real OpenAI API tests; skipped when `OPENAI_API_KEY` is not set.
