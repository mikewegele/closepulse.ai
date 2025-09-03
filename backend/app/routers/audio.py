import os
import wave

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text

from ..config import settings
from ..db import SessionLocal
from ..services.snapshot_audio import _find_audio_path

router = APIRouter()


@router.get("/audio/{call_id}.wav")
def get_audio(call_id: str):
    p = _find_audio_path(call_id)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(p, media_type="audio/wav", filename=f"{call_id}.wav")


@router.get("/audio/_debug/{call_id}")
def debug_audio(call_id: str):
    p = _find_audio_path(call_id)
    ap = os.path.abspath(p) if p else None
    return JSONResponse({
        "call_id": call_id,
        "path": p,
        "abs_path": ap,
        "cwd": os.getcwd(),
        "exists": os.path.exists(ap) if ap else False,
        "isfile": os.path.isfile(ap) if ap else False,
        "readable": (os.access(ap, os.R_OK) if ap and os.path.exists(ap) else False),
    })


def _wav_info(path: str):
    info = {"exists": False}
    try:
        if not os.path.exists(path):
            return info
        info["exists"] = True
        info["size_bytes"] = os.path.getsize(path)
        with wave.open(path, "rb") as r:
            n = r.getnframes();
            sr = r.getframerate()
            info.update({
                "frames": n,
                "samplerate": sr,
                "channels": r.getnchannels(),
                "sampwidth": r.getsampwidth(),
                "duration_sec": round(n / float(sr or 1), 3),
            })
    except Exception as e:
        info["error"] = str(e)
    return info


@router.get("/audio/_stats/{call_id}")
async def audio_stats(call_id: str):
    p = _find_audio_path(call_id)
    ap = os.path.abspath(p) if p else None
    wav = _wav_info(ap) if ap else {"exists": False}
    db_row = None
    try:
        async with SessionLocal() as db:
            res = await db.execute(
                text("""select conversation_id, external_id, audio_path, chunk_count, audio_bytes_total, updated_at
                        from live_calls
                        where conversation_id = :cid
                        order by updated_at desc limit 1"""),
                {"cid": call_id}
            )
            row = res.mappings().first()
            if row:
                db_row = dict(row)
    except Exception as e:
        db_row = {"error": str(e)}
    return JSONResponse({
        "call_id": call_id,
        "path": p,
        "abs_path": ap,
        "wav": wav,
        "db": db_row,
        "cwd": os.getcwd(),
        "AUDIO_DIR": getattr(settings, "AUDIO_DIR", "./audio"),
    })
