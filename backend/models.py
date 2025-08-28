# backend/models.py
from datetime import datetime
from typing import Optional, List

from sqlalchemy import String, Text, DateTime, JSON, ForeignKey, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CallSession(Base):
    __tablename__ = "call_sessions"
    call_id: Mapped[str] = mapped_column(String(128), primary_key=True)  # v3:…
    from_number: Mapped[str | None] = mapped_column(String(32))
    to_number: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(String(128), index=True)
    t_start: Mapped[int] = mapped_column(Integer)  # ms optional
    t_end: Mapped[int] = mapped_column(Integer)  # ms optional
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    messages: Mapped[List["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(32))  # "user"
    content: Mapped[str] = mapped_column(Text)  # anonymisierter Transkript-Text
    source: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    # Traffic Light Felder (NULL erlaubt)
    traffic_light: Mapped[Optional[str]] = mapped_column(String(16), index=True, default=None)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
