import time
import wave
from io import BytesIO
from typing import Optional

import audioop
import openai
from fastapi import APIRouter, UploadFile, File, HTTPException, Header

from ..config import settings
from ..logging import setup_logging

log = setup_logging()
router = APIRouter()

TARGET_RATE = 16000
TARGET_WIDTH = 2
TARGET_CHANNELS = 1
MIN_SAMPLES = 3200  # ~0.2s


def _force_wav_16k_mono_s16(raw: bytes) -> bytes:
    bio_in = BytesIO(raw)
    try:
        with wave.open(bio_in, "rb") as r:
            ch = r.getnchannels()
            sw = r.getsampwidth()
            fr = r.getframerate()
            n = r.getnframes()
            if n <= 0:
                return b""
            pcm = r.readframes(n)

        if ch == 2:
            pcm = audioop.tomono(pcm, sw, 1.0, 1.0);
            ch = 1
        elif ch != 1:
            pcm = audioop.tomono(pcm, sw, 1.0, 0.0);
            ch = 1

        if sw != TARGET_WIDTH:
            pcm = audioop.lin2lin(pcm, sw, TARGET_WIDTH);
            sw = TARGET_WIDTH

        if fr != TARGET_RATE:
            pcm, _ = audioop.ratecv(pcm, TARGET_WIDTH, TARGET_CHANNELS, fr, TARGET_RATE, None);
            fr = TARGET_RATE

        out = BytesIO()
        with wave.open(out, "wb") as w:
            w.setnchannels(TARGET_CHANNELS)
            w.setsampwidth(TARGET_WIDTH)
            w.setframerate(TARGET_RATE)
            w.writeframes(pcm)
        return out.getvalue()
    except Exception:
        return b""


@router.post("/transcribe")
async def transcribe(
        file: UploadFile = File(...),
        x_conversation_id: Optional[str] = Header(default=None),
):
    t0 = time.perf_counter()
    try:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=422, detail="No audio payload")

        wav_bytes = _force_wav_16k_mono_s16(raw)
        if not wav_bytes:
            raise HTTPException(status_code=400, detail="Unsupported or corrupted audio")

        with wave.open(BytesIO(wav_bytes), "rb") as r:
            if r.getnframes() < MIN_SAMPLES:
                # zu kurz -> kein Fehler, aber auch kein Text
                return {"text": "", "duration": time.perf_counter() - t0, "conversation_id": x_conversation_id}

        bio = BytesIO(wav_bytes);
        bio.seek(0)
        tr = openai.audio.transcriptions.create(
            file=("chunk.wav", bio, "audio/wav"),
            model=settings.TRANSCRIBE_MODEL,
            # language=settings.TRANSCRIBE_LANG,  # optional
        )
        text = (getattr(tr, "text", "") or "").strip()
        return {"text": text, "duration": time.perf_counter() - t0, "conversation_id": x_conversation_id}
    except HTTPException:
        raise
    except openai.BadRequestError as e:
        raise HTTPException(status_code=400, detail=f"OpenAI rejected audio: {e}") from e
    except Exception as e:
        log.exception("transcribe failed: %s", e)
        raise HTTPException(status_code=500, detail=f"transcribe failed: {e}") from e
