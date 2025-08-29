from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    TELNYX_API_KEY: str
    DATABASE_URL: str = "sqlite+aiosqlite:///./closepulse.db"
    CLOSEPULSE_CORS: Optional[str] = None
    ASK_TIMEOUT: float = 25.0
    TL_TIMEOUT: float = 15.0
    TRANSCRIBE_MODEL: str = "whisper-1"
    TRANSCRIBE_LANG: str = "de"
    LOG_LEVEL: str = "INFO"
    WS_BASE: str
    PUBLIC_BASE: str
    STORE_MODE: str = "on_demand"  # "always" | "on_demand" | "never"
    EXTERNAL_CALL_ID: str
    AUDIO_DIR: str

    class Config:
        env_file = ".env"


settings = Settings()
