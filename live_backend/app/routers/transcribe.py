# app/routers/transcribe.py
import time
import wave
from io import BytesIO
from pathlib import Path
from typing import Literal

import audioop
import openai
from fastapi import APIRouter, File, UploadFile, HTTPException, Header

from ..config import settings
from ..services.persist import anonymize_and_store

router = APIRouter()
TARGET_SR = 16000
recordings_dir = Path("recordings")
recordings_dir.mkdir(exist_ok=True)


def _to_wav16k_mono(raw: bytes) -> bytes:
    bio = BytesIO(raw)
    with wave.open(bio, "rb") as r:
        ch = r.getnchannels()
        sw = r.getsampwidth()
        sr = r.getframerate()
        frames = r.readframes(r.getnframes())
    if ch == 2:
        frames = audioop.tomono(frames, sw, 0.5, 0.5)
    if sr != TARGET_SR:
        frames, _ = audioop.ratecv(frames, sw, 1, sr, TARGET_SR, None)
    out = BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TARGET_SR)
        w.writeframes(frames)
    return out.getvalue()


@router.post("/transcribe")
async def transcribe(
        file: UploadFile = File(...),
        x_conversation_id: str | None = Header(default=None),
):
    t0 = time.perf_counter()
    raw = await file.read()
    if not raw:
        raise HTTPException(422, "No audio")
    wav_bytes = _to_wav16k_mono(raw)
    tr = openai.audio.transcriptions.create(
        file=("chunk.wav", BytesIO(wav_bytes), "audio/wav"),
        model=settings.TRANSCRIBE_MODEL,
        language=settings.TRANSCRIBE_LANG,
    )
    text = (getattr(tr, "text", "") or "").strip()
    if text:
        await anonymize_and_store(text, "audio/wav", file.filename, x_conversation_id)
    return {
        "text": text,
        "duration": time.perf_counter() - t0,
        "conversation_id": x_conversation_id,
    }


async def transcribe_by_ext(ext_id: str, leg: Literal["mic", "spk"] = "spk") -> str:
    wavs = sorted(recordings_dir.glob(f"{ext_id}-*-{leg}.wav"))
    if not wavs:
        return ""
    latest = wavs[-1]
    raw = latest.read_bytes()
    wav_bytes = _to_wav16k_mono(raw)
    tr = openai.audio.transcriptions.create(
        file=("chunk.wav", BytesIO(wav_bytes), "audio/wav"),
        model=settings.TRANSCRIBE_MODEL,
        language=settings.TRANSCRIBE_LANG,
    )
    return (getattr(tr, "text", "") or "").strip()
