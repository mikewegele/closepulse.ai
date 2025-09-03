# app/routes/ext_audio.py
from __future__ import annotations

import glob
import os
import wave
from typing import Optional

import httpx
from fastapi import APIRouter, Query, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from backend.config import settings
from ..logging import setup_logging

log = setup_logging()
router = APIRouter()

# Basis-Config
PUBLIC_BASE = (getattr(settings, "PUBLIC_BASE", "") or "http://127.0.0.1:8000").rstrip("/")
AUDIO_DIR = getattr(settings, "AUDIO_DIR", "./recordings")
os.makedirs(AUDIO_DIR, exist_ok=True)

ANALYZE_URL = f"{PUBLIC_BASE}/analyze_fast"
# store=0 -> nur transkribieren, nichts persistieren
TRANSCRIBE_URL = f"{PUBLIC_BASE}/transcribe?store=0"


def _latest_audio_for_ext_id(ext_id: str) -> Optional[str]:
    """
    Sucht die *neueste* Datei nach mtime: <AUDIO_DIR>/<ext_id>-*.wav
    """
    pattern = os.path.join(AUDIO_DIR, f"{ext_id}-*.wav")
    files = glob.glob(pattern)
    if not files:
        return None
    files.sort(key=lambda p: os.path.getmtime(p))
    return files[-1]


def _wav_info(path: str) -> dict:
    info = {"exists": False}
    try:
        if not path or not os.path.isfile(path):
            return info
        info["exists"] = True
        info["size_bytes"] = os.path.getsize(path)
        with wave.open(path, "rb") as r:
            n = r.getnframes()
            sr = r.getframerate()
            ch = r.getnchannels()
            sw = r.getsampwidth()
        info.update({
            "frames": n,
            "samplerate": sr,
            "channels": ch,
            "sampwidth": sw,
            "duration_sec": round(n / float(sr or 1), 3),
            "basename": os.path.basename(path),
        })
    except Exception as e:
        info["error"] = str(e)
    return info


# ---------- AUDIO HOLEN PER EXTERNAL ID ----------

@router.get("/audio/by_ext/{ext_id}.wav")
def get_audio_by_ext(ext_id: str, path: Optional[str] = Query(default=None)):
    """
    Liefert die neueste WAV-Datei für ext_id (oder expliziten path, wenn angegeben).
    """
    audio_path = path or _latest_audio_for_ext_id(ext_id)
    if not audio_path or not os.path.isfile(audio_path):
        raise HTTPException(404, f"no audio for ext_id={ext_id}")
    return FileResponse(audio_path, media_type="audio/wav", filename=os.path.basename(audio_path))


@router.get("/audio/_stats_by_ext/{ext_id}")
def audio_stats_by_ext(ext_id: str, path: Optional[str] = Query(default=None)):
    audio_path = path or _latest_audio_for_ext_id(ext_id)
    ap = os.path.abspath(audio_path) if audio_path else None
    info = _wav_info(ap) if ap else {"exists": False}
    return JSONResponse({
        "ext_id": ext_id,
        "audio_dir": AUDIO_DIR,
        "path": audio_path,
        "abs_path": ap,
        "wav": info,
        "cwd": os.getcwd(),
        "public_base": PUBLIC_BASE,
        "transcribe_url": TRANSCRIBE_URL,
        "analyze_url": ANALYZE_URL,
    })


# ---------- TRANSCRIBE PER EXTERNAL ID ----------

@router.post("/transcribe/by_ext")
async def transcribe_by_ext(
        ext_id: Optional[str] = Query(default=None),
        call_id: Optional[str] = Query(default=None),  # Alias erlaubt
        path: Optional[str] = Query(default=None),
        x_conversation_id: Optional[str] = Header(default=None),
        timeout_s: int = Query(default=300),
):
    """
    Lädt die neueste WAV für ext_id (oder call_id als Alias) und ruft euren /transcribe-Endpoint auf.
    """
    use_ext = ext_id or call_id
    if not use_ext:
        raise HTTPException(422, "need ext_id or call_id")

    audio_path = path or _latest_audio_for_ext_id(use_ext)
    if not audio_path or not os.path.isfile(audio_path):
        raise HTTPException(404, f"no audio for id={use_ext}")

    try:
        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
            headers = {"x-conversation-id": x_conversation_id or use_ext}
            async with httpx.AsyncClient(timeout=timeout_s, headers=headers) as c:
                tr = await c.post(TRANSCRIBE_URL, files=files)
                tr.raise_for_status()
                if tr.headers.get("content-type", "").startswith("application/json"):
                    tj = tr.json()
                    text = (tj.get("text") or "").strip()
                else:
                    text = ""
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"transcribe upstream: {e}") from e
    except Exception as e:
        raise HTTPException(502, f"transcription failed: {e}") from e

    return {
        "ext_id": use_ext,
        "audio": os.path.basename(audio_path),
        "text": text,
    }


# ---------- SUGGESTIONS = TRANSCRIBE + ANALYZE ----------

@router.post("/suggest_audio")
async def suggest_audio(
        ext_id: Optional[str] = Query(default=None),
        call_id: Optional[str] = Query(default=None),  # Alias erlaubt
        x_conversation_id: Optional[str] = Header(default=None),
        path: Optional[str] = Query(default=None),
        timeout_s: int = Query(default=300),
        include_text: bool = Query(default=False),
):
    """
    1) Holt neueste WAV per ext_id (oder call_id)
    2) Transkribiert via /transcribe (store=0)
    3) Analysiert via /analyze_fast
    """
    use_ext = ext_id or call_id
    if not use_ext:
        raise HTTPException(422, "need ext_id or call_id")

    audio_path = path or _latest_audio_for_ext_id(use_ext)
    if not audio_path or not os.path.isfile(audio_path):
        raise HTTPException(404, f"no audio for id={use_ext}")

    # 1) TRANSCRIBE
    try:
        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
            t_headers = {"x-conversation-id": x_conversation_id or use_ext}
            async with httpx.AsyncClient(timeout=timeout_s, headers=t_headers) as c:
                tr = await c.post(TRANSCRIBE_URL, files=files)
                tr.raise_for_status()
                if tr.headers.get("content-type", "").startswith("application/json"):
                    tj = tr.json()
                else:
                    tj = {}
                text = (tj.get("text") or "").strip()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"transcribe upstream: {e}") from e
    except Exception as e:
        raise HTTPException(502, f"transcription failed: {e}") from e

    if not text:
        raise HTTPException(422, "empty transcript")

    # 2) ANALYZE
    payload = [{"role": "user", "content": text}]
    a_headers = {"Content-Type": "application/json", "x-conversation-id": x_conversation_id or use_ext}
    try:
        async with httpx.AsyncClient(timeout=timeout_s, headers=a_headers) as c:
            r = await c.post(ANALYZE_URL, json=payload)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"analyze upstream: {e}") from e
    except Exception as e:
        raise HTTPException(502, f"analyze failed: {e}") from e

    out = {
        "suggestions": data.get("suggestions", []),
        "trafficLight": data.get("trafficLight", {}),
        "source": {"ext_id": use_ext, "audio": os.path.basename(audio_path)},
    }
    if include_text:
        out["text"] = text
    return out
