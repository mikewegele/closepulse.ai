# backend/models.py
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, JSON, func, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(32))  # "user"
    content: Mapped[str] = mapped_column(Text)  # finaler, anonymisierter Text (nur bei Hangup)
    source: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class LiveCall(Base):
    __tablename__ = "live_calls"
    conversation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), default="")
    audio_path: Mapped[str] = mapped_column(String(512))  # Pfad zur wachsenden .wav
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    audio_bytes_total: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
