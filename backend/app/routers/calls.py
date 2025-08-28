# app/routers/calls.py
from fastapi import APIRouter, HTTPException
from models import TranscriptChunk
from sqlalchemy import select

from ..db import Session

router = APIRouter()


@router.get("/calls/{call_id}/transcript")
async def get_transcript(call_id: str, since_seconds: int | None = None, max_chars: int = 4000):
    async with Session() as s:
        q = select(TranscriptChunk).where(TranscriptChunk.call_id == call_id).order_by(TranscriptChunk.id.asc())
        rows = (await s.execute(q)).scalars().all()
    if not rows:
        raise HTTPException(404, "no transcript")
    text = " ".join(r.text for r in rows)
    return {"call_id": call_id, "text": text[:max_chars]}
