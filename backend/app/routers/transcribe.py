import time
import wave
from io import BytesIO

import audioop
import openai
from fastapi import APIRouter, HTTPException, File, UploadFile, Header

from ..config import settings
from ..logging import setup_logging
from ..services.anonymize import anonymize_and_store

log = setup_logging()
router = APIRouter()

TARGET_SR = 16000


def _to_wav16k_mono_with_padding(raw_wav: bytes, pad_ms: int = 250) -> bytes:
    try:
        bio = BytesIO(raw_wav)
        with wave.open(bio, "rb") as r:
            ch = r.getnchannels()
            sw = r.getsampwidth()
            sr = r.getframerate()
            frames = r.readframes(r.getnframes())
        if ch == 2:
            frames = audioop.tomono(frames, sw, 0.5, 0.5)
            ch = 1
        if sr != TARGET_SR:
            frames = audioop.ratecv(frames, sw, ch, sr, TARGET_SR, None)[0]
            sr = TARGET_SR
        pad_bytes = int(pad_ms * TARGET_SR / 1000) * 2
        silence = b"\x00" * pad_bytes
        frames = silence + frames + silence
        out = BytesIO()
        with wave.open(out, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(TARGET_SR)
            w.writeframes(frames)
        return out.getvalue()
    except Exception as e:
        log.warning("normalize/pad failed: %s", e)
        return raw_wav


@router.post("/transcribe")
async def transcribe(
        file: UploadFile = File(...),
        x_conversation_id: str | None = Header(default=None),
        store: int = Query(default=0),
):
    t0 = time.perf_counter()
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="No audio payload")
    wav_bytes = _to_wav16k_mono_with_padding(raw, pad_ms=250)
    try:
        with wave.open(BytesIO(wav_bytes), "rb") as r:
            if r.getnframes() < int(0.8 * TARGET_SR):
                return {"text": "", "duration": time.perf_counter() - t0, "conversation_id": x_conversation_id,
                        "note": "too short for reliable ASR"}
    except Exception as e:
        raise HTTPException(400, f"Invalid WAV: {e}")
    lang = getattr(settings, "TRANSCRIBE_LANG", None) or "de"
    try:
        tr = openai.audio.transcriptions.create(
            file=("chunk.wav", BytesIO(wav_bytes), "audio/wav"),
            model=settings.TRANSCRIBE_MODEL,
            language=lang,
        )
        text = (getattr(tr, "text", "") or "").strip()
        if store and text:
            await anonymize_and_store(text=text, mime="text/plain", name=file.filename or "chunk.wav",
                                      x_conversation_id=x_conversation_id)
        return {"text": text, "duration": time.perf_counter() - t0, "conversation_id": x_conversation_id}
    except openai.BadRequestError as e:
        raise HTTPException(status_code=400, detail=f"OpenAI rejected audio: {e}") from e
    except Exception as e:
        log.exception("transcribe failed: %s", e)
        raise HTTPException(status_code=500, detail=f"transcribe failed: {e}") from e
