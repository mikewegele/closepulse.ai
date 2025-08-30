import glob
import os

import httpx
from fastapi import APIRouter, Query, Header, HTTPException

from ..config import settings
from ..services.snapshot import save_snapshot
from ..state.live_store import live_store

router = APIRouter()
ANALYZE_URL = f"{settings.PUBLIC_BASE}/analyze_fast"
TRANSCRIBE_URL = f"{settings.PUBLIC_BASE}/transcribe?store=0"
AUDIO_DIR = settings.AUDIO_DIR


@router.api_route("/suggest", methods=["GET", "POST"])
async def suggest(call_id: str = Query(...), save: bool = Query(default=True),
                  x_conversation_id: str | None = Header(default=None)):
    if save:
        await save_snapshot(call_id, reason="button")
    text = (live_store.full_text(call_id) or "").strip()
    if not text:
        raise HTTPException(404, "no transcript in memory for call_id")
    payload = [{"role": "user", "content": text}]
    headers = {"Content-Type": "application/json", "x-conversation-id": x_conversation_id or call_id}
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as c:
        r = await c.post(ANALYZE_URL, json=payload);
        r.raise_for_status();
        data = r.json()
    return {"suggestions": data.get("suggestions", []), "trafficLight": data.get("trafficLight", {})}


def _latest_audio_for_ext_id(ext_id: str) -> str | None:
    pattern = os.path.join(AUDIO_DIR, f"{ext_id}-*.wav")
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


@router.post("/suggest_audio")
async def suggest_audio(ext_id: str = Query(...), x_conversation_id: str | None = Header(default=None),
                        path: str | None = Query(default=None), timeout_s: int = Query(default=300)):
    audio_path = path or _latest_audio_for_ext_id(ext_id)
    if not audio_path or not os.path.isfile(audio_path):
        raise HTTPException(404, "no audio for ext_id")
    try:
        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
            async with httpx.AsyncClient(timeout=timeout_s) as c:
                tr = await c.post(TRANSCRIBE_URL, files=files, headers={"x-conversation-id": ext_id})
                tr.raise_for_status()
                tj = tr.json() if tr.headers.get("content-type", "").startswith("application/json") else {}
                text = (tj.get("text") or "").strip()
    except Exception:
        raise HTTPException(502, "transcription failed")
    if not text:
        raise HTTPException(422, "empty transcript")
    payload = [{"role": "user", "content": text}]
    headers = {"Content-Type": "application/json", "x-conversation-id": x_conversation_id or ext_id}
    async with httpx.AsyncClient(timeout=60.0, headers=headers) as c:
        r = await c.post(ANALYZE_URL, json=payload);
        r.raise_for_status();
        data = r.json()
    return {"suggestions": data.get("suggestions", []), "trafficLight": data.get("trafficLight", {}),
            "source": {"ext_id": ext_id, "audio": os.path.basename(audio_path)}}
