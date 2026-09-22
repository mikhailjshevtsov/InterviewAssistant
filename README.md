# Interview AI Assistant MVP

Telegram AI-assistant for interview preparation.

## Stack
- Python 3.12+
- aiogram 3.x
- OpenAI API
- SQLite
- CSV Knowledge Base

## Current stage
Stage 2: persistent storage (SQLite + async SQLAlchemy). Users, vacancies and interview sessions are saved to `data/app.db`; tables are created on startup via `metadata.create_all`. OpenAI integration is intentionally not implemented yet.

## Run
1. Create `.env` from `.env.example`
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `python -m app.main`

## Tests
`python -m pytest` — tests use a temporary SQLite database, never `data/app.db`.
