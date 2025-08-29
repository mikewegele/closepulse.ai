import asyncio
import os
from datetime import datetime
from typing import Optional, Dict

from fastapi import HTTPException, UploadFile
from models import Message
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession


def now_berlin() -> datetime:
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("Europe/Berlin")
        return datetime.now(tz=tz)
    except Exception:
        return datetime.utcnow()


def now_berlin_iso_date() -> str:
    return now_berlin().date().isoformat()


def system_date_message() -> Dict[str, str]:
    return {"role": "system", "content": f"Heute ist der {now_berlin_iso_date()}"}


async def with_timeout(coro, timeout: float, label: str):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"{label} timed out after {timeout}s")


def safe_mime_from_upload(file: UploadFile) -> str:
    return file.content_type or "application/octet-stream"


async def add_message(
        db: AsyncSession,
        conversation_id: str,
        role: str,
        content: str,
        source: Optional[str] = None,
        meta: Optional[dict] = None,
):
    msg = Message(
        conversation_id=conversation_id,
        external_id=os.getenv("EXTERNAL_CALL_ID", "EXT_FIXED_ID"),
        role=role,
        content=content,
        source=source,
        created_at=now_berlin(),
        meta=meta or {},
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def update_message_tl(db: AsyncSession, message_id: int, traffic_light: Optional[str]):
    await db.execute(
        sa_update(Message).where(Message.id == message_id).values(traffic_light=traffic_light)
    )
    await db.commit()
