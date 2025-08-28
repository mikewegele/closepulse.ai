# app/routers/suggest.py
import httpx
from fastapi import APIRouter, HTTPException, Header, Query
from models import TranscriptChunk
from pydantic import BaseModel
from sqlalchemy import select

from ..config import settings  # <— nicht ".. import settings"
from ..db import Session  # <— aus db.py holen

router = APIRouter()
ANALYZE_URL = f"{settings.PUBLIC_BASE}/analyze_fast"


class SuggestResponse(BaseModel):
    suggestions: list[str] = []
    trafficLight: dict = {}


@router.post("/suggest", response_model=SuggestResponse)
async def suggest(
        call_id: str = Query(...),
        x_conversation_id: str | None = Header(default=None)
):
    async with Session() as s:
        rows = (await s.execute(
            select(TranscriptChunk)
            .where(TranscriptChunk.call_id == call_id)
            .order_by(TranscriptChunk.id.asc())
        )).scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail="no transcript")

    text = " ".join(r.text for r in rows)

    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(
            ANALYZE_URL,
            json=[{"role": "user", "content": text}],
            headers={"x-conversation-id": x_conversation_id or call_id}
        )
        r.raise_for_status()
        data = r.json()

    return SuggestResponse(
        suggestions=data.get("suggestions", []),
        trafficLight=data.get("trafficLight", {})
    )
