from urllib.parse import quote

from pydantic import computed_field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    PG_POOL_MAX: int = 10

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_FALLBACK_MODEL: str = "gemini-2.5-flash"
    GEMINI_MAX_RETRIES: int = 5
    GEMINI_RETRY_BASE_DELAY_SECONDS: float = 1.0
    GEMINI_MAX_BACKOFF_SECONDS: float = 8.0
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    CHAKULA_API_KEY: str = ""

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        # quote(..., safe="") percent-encodes ALL special chars (e.g. @ → %40, / → %2F)
        # so passwords like "pass./" are never mis-parsed as part of the URL path.
        encoded_password = quote(self.POSTGRES_PASSWORD, safe="")
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{encoded_password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = {"extra": "ignore"}


settings = Settings()
