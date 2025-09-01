import os


class Settings:
    TRANSCRIBE_MODEL = os.getenv("TRANSCRIBE_MODEL", "whisper-1")
    TRANSCRIBE_LANG = os.getenv("TRANSCRIBE_LANG", "de")
    ASK_TIMEOUT = int(os.getenv("ASK_TIMEOUT", 20))
    TL_TIMEOUT = int(os.getenv("TL_TIMEOUT", 8))
    NEON_URL = os.getenv("NEON_URL", "postgresql+asyncpg://user:pass@host/db?sslmode=require")
    OPENAI_API_KEY: os.getenv("OPENAI_API_KEY", "de")


settings = Settings()
