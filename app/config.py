from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://chakula:chakula_secret@db:5432/chakula"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_FALLBACK_MODEL: str = "gemini-2.5-flash"
    GEMINI_MAX_RETRIES: int = 5
    GEMINI_RETRY_BASE_DELAY_SECONDS: float = 1.0
    GEMINI_MAX_BACKOFF_SECONDS: float = 8.0
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    CHAKULA_API_KEY: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
