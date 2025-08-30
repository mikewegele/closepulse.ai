# app/services/live_audio.py
import os
import wave
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import audioop
from models import LiveCall
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..logging import setup_logging

log = setup_logging()

AUDIO_DIR = getattr(settings, "AUDIO_DIR", "./audio")
os.makedirs(AUDIO_DIR, exist_ok=True)


def _conv_8k_lin16_to_16k(pcm8k: bytes) -> bytes:
    if not pcm8k:
        return b""
    new, _ = audioop.ratecv(pcm8k, 2, 1, 8000, 16000, None)
    return new


def _append_wav16_mono(path: str, pcm16: bytes) -> int:
    """
    Hängt PCM16/16k/mono an eine WAV-Datei an (erstellt sie bei Bedarf).
    Gibt die Anzahl der *angenhängten Bytes im WAV-Datenbereich* zurück.
    """
    if not pcm16:
        return 0
    appended = 0
    if not os.path.exists(path):
        # Neu anlegen mit korrekten Parametern
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm16)
            appended = len(pcm16)
    else:
        # Bestehende Datei öffnen und Frames anhängen
        with wave.open(path, "rb") as r:
            params = r.getparams()
            if params.nchannels != 1 or params.sampwidth != 2 or params.framerate != 16000:
                raise ValueError(f"Unexpected WAV format in {path}: {params}")
            existing_frames = r.getnframes()
            existing_data = r.readframes(existing_frames)

        # Neu schreiben (Header + alt + neu), um Header sicher zu aktualisieren
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(existing_data)
            w.writeframes(pcm16)
            appended = len(pcm16)
    return appended


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
        # Pfad/Ext ggf. updaten
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
    """
    1) 8k-PCM16 → 16k-PCM16 konvertieren
    2) an eine WAV pro conversation_id anhängen
    3) live_calls updaten (eine Zeile)
    Gibt den Dateipfad zurück.
    """
    # Dateiname pro conversation_id stabil
    fname = f"{conversation_id}.wav"
    fpath = os.path.join(AUDIO_DIR, fname)

    # 8k -> 16k
    pcm16 = _conv_8k_lin16_to_16k(pcm8k_lin16)
    appended = _append_wav16_mono(fpath, pcm16)

    # DB-Row upsert + Metriken erhöhen
    async with db.begin():
        row = await _get_or_create_live_row(db, conversation_id, external_id, fpath, meta=meta)
        row.chunk_count += 1
        row.audio_bytes_total += appended
        row.updated_at = datetime.now(timezone.utc)
        await db.flush()

    return fpath
