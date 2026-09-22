from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    bot_token: str
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-mini"
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()
