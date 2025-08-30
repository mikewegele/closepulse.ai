import os
import wave
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from models import LiveCall
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..logging import setup_logging

log = setup_logging()

AUDIO_DIR = getattr(settings, "AUDIO_DIR", "./audio")
os.makedirs(AUDIO_DIR, exist_ok=True)


def _append_wav8_mono(path: str, pcm8k_s16: bytes) -> int:
    if not pcm8k_s16:
        return 0
    if not os.path.exists(path):
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(pcm8k_s16)
        return len(pcm8k_s16)
    with wave.open(path, "rb") as r:
        params = r.getparams()
        if params.nchannels != 1 or params.sampwidth != 2 or params.framerate != 8000:
            raise ValueError(f"Unexpected WAV format in {path}: {params}")
        existing = r.readframes(r.getnframes())
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(existing)
        w.writeframes(pcm8k_s16)
    return len(pcm8k_s16)


def _probe_wav(path: str) -> dict:
    info = {"exists": False}
    try:
        if not os.path.exists(path):
            return info
        info["exists"] = True
        info["size_bytes"] = os.path.getsize(path)
        with wave.open(path, "rb") as r:
            nframes = r.getnframes()
            rate = r.getframerate()
            ch = r.getnchannels()
            sw = r.getsampwidth()
            info.update({
                "frames": nframes,
                "samplerate": rate,
                "channels": ch,
                "sampwidth": sw,
                "duration_sec": round(nframes / float(rate or 1), 3),
            })
        return info
    except Exception as e:
        info["error"] = str(e)
        return info


async def _get_or_create_live_row(
        db: AsyncSession,
        conversation_id: str,
        external_id: str,
        audio_path: str,
        meta: Optional[Dict[str, Any]] = None,
) -> LiveCall:
    now = datetime.now(timezone.utc)
    stmt = select(LiveCall).where(LiveCall.conversation_id == conversation_id).with_for_update()
    res = await db.execute(stmt)
    row: Optional[LiveCall] = res.scalars().first()
    if row:
        if not row.audio_path:
            row.audio_path = audio_path
        if external_id and (not row.external_id):
            row.external_id = external_id
        row.updated_at = now
        if meta:
            merged = dict(row.meta or {})
            merged.update(meta)
            row.meta = merged
        await db.flush()
        return row
    row = LiveCall(
        conversation_id=conversation_id,
        external_id=external_id,
        audio_path=audio_path,
        chunk_count=0,
        audio_bytes_total=0,
        created_at=now,
        updated_at=now,
        meta=meta or {},
    )
    db.add(row)
    await db.flush()
    return row


async def append_audio_chunk(
        db: AsyncSession,
        conversation_id: str,
        external_id: str,
        pcm8k_lin16: bytes,
        meta: Optional[Dict[str, Any]] = None,
) -> str:
    fname = f"{conversation_id}.wav"
    fpath = os.path.join(AUDIO_DIR, fname)
    appended = _append_wav8_mono(fpath, pcm8k_lin16)
    async with db.begin():
        row = await _get_or_create_live_row(db, conversation_id, external_id, fpath, meta=meta)
        row.chunk_count += 1
        row.audio_bytes_total += appended
        row.updated_at = datetime.now(timezone.utc)
        await db.flush()
    wav_info = _probe_wav(fpath)
    log.info("append_audio_chunk: conv=%s ext=%s +%dB -> total_bytes=%d | wav=%s", conversation_id, external_id,
             appended, row.audio_bytes_total, wav_info)
    return fpath
