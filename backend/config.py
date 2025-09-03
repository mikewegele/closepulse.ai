# backend/config.py
import os
from typing import Optional

from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    OPENAI_API_KEY: str = Field(
        validation_alias=AliasChoices("OPENAI_API_KEY", "CP_OPENAI_API_KEY", "VITE_OPENAI_API_KEY")
    )
    DATABASE_URL: str = "sqlite+aiosqlite:///./closepulse.db"
    CLOSEPULSE_CORS: Optional[str] = None
    ASK_TIMEOUT: float = 25.0
    TL_TIMEOUT: float = 15.0
    TRANSCRIBE_MODEL: str = "whisper-1"
    TRANSCRIBE_LANG: str = "de"
    LOG_LEVEL: str = "INFO"
    WS_BASE: str
    REALTIME_MODEL: str = Field(default="gpt-4o-mini-transcribe",
                                validation_alias=AliasChoices("REALTIME_MODEL", "CP_REALTIME_MODEL"))
    PUBLIC_BASE: str
    STORE_MODE: str = "on_demand"
    EXTERNAL_CALL_ID: str
    AUDIO_DIR: str


settings = Settings()

# >>> WICHTIG: OpenAI erwartet diese ENV-Variable <<<
os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)
