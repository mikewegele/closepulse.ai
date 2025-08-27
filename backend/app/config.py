from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    DATABASE_URL: str = "sqlite+aiosqlite:///./closepulse.db"
    CLOSEPULSE_CORS: Optional[str] = None
    ASK_TIMEOUT: float = 25.0
    TL_TIMEOUT: float = 15.0
    TRANSCRIBE_MODEL: str = "whisper-1"
    TRANSCRIBE_LANG: str = "de"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()
