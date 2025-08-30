import asyncio
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import HTTPException, UploadFile
from models import Message
from sqlalchemy import update as sa_update, select
from sqlalchemy.exc import IntegrityError
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


def _ensure_conv_id(conversation_id: Optional[str], external_id: Optional[str]) -> str:
    # absolut niemals NULL in DB schreiben
    if conversation_id and conversation_id.strip():
        return conversation_id.strip()
    if external_id and external_id.strip():
        return external_id.strip()
    return "unknown"


async def _append_into_single_row(
        db: AsyncSession,
        conversation_id: Optional[str],
        role: str,
        content: str,
        source: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        external_id: Optional[str] = None,
) -> int:
    """
    EXACTLY ONE ROW per conversation_id:
    - Sucht die Zeile und sperrt sie (SELECT ... FOR UPDATE)
    - hängt content an und merged meta
    - legt sie nur bei der ersten Benutzung an (INSERT)
    """
    cid = _ensure_conv_id(conversation_id, external_id)
    ext = external_id or cid
    content = (content or "").strip()
    meta = meta or {}
    now_utc = datetime.now(timezone.utc)

    # Eine Transaktion; commit erfolgt automatisch beim Verlassen des Kontextes.
    async with db.begin():
        # Exklusiv sperren, damit keine parallelen Inserts passieren
        stmt = select(Message).where(Message.conversation_id == cid).with_for_update()
        res = await db.execute(stmt)
        row: Optional[Message] = res.scalars().first()

        if row is not None:
            # UPDATE/APPEND
            if content:
                row.content = (row.content + (" " if row.content and content else "") + content).strip()
            # halte role/source aktuell (optional)
            if role:
                row.role = role
            if source:
                row.source = source
            if ext and not row.external_id:
                row.external_id = ext

            # Meta flach mergen
            if isinstance(row.meta, dict):
                merged = dict(row.meta)
                merged.update(meta)
                row.meta = merged
            else:
                row.meta = meta

            # created_at bleibt unverändert
            await db.flush()
            return row.id

        # INSERT (erstes Mal für diese conversation_id)
        new_row = Message(
            conversation_id=cid,
            external_id=ext,
            role=role,
            content=content,
            source=source,
            created_at=now_utc,
            meta=meta,
        )
        db.add(new_row)
        await db.flush()
        return new_row.id


async def add_message_live(
        db: AsyncSession,
        conversation_id: Optional[str],
        role: str,
        content: str,
        source: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        external_id: Optional[str] = None,
) -> int:
    try:
        return await _append_into_single_row(
            db=db,
            conversation_id=conversation_id,
            role=role,
            content=content,
            source=source,
            meta=meta,
            external_id=external_id,
        )
    except IntegrityError:
        # Falls parallel der allererste INSERT kollidiert hat, nochmal versuchen (idempotent)
        return await _append_into_single_row(
            db=db,
            conversation_id=conversation_id,
            role=role,
            content=content,
            source=source,
            meta=meta,
            external_id=external_id,
        )
