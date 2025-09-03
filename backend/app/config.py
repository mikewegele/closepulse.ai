from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="CP_"  # nur Variablen mit CP_ werden eingelesen
    )
    openai_api_key: str
    allowed_origins: List[str] = ["http://localhost:5173", "http://localhost:3000"]
    realtime_model: str = "gpt-4o-mini-transcribe"
