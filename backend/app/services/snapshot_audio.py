import os
import wave
from io import BytesIO
from typing import Optional

import openai
from sqlalchemy import text

from ..config import settings
from ..db import SessionLocal
from ..logging import setup_logging
from ..services.anonymize import anonymize_and_store

log = setup_logging()
AUDIO_DIR = getattr(settings, "AUDIO_DIR", "./audio")
MIN_SECONDS = float(getattr(settings, "FINAL_MIN_SECONDS", 1.0))
DEFAULT_LANG = getattr(settings, "TRANSCRIBE_LANG", None) or "de"


def _find_audio_path(call_id: str) -> Optional[str]:
    candidates = [getattr(settings, "AUDIO_DIR", "./audio"), "./recordings", "."]
    for base in candidates:
        p = os.path.join(base, f"{call_id}.wav")
        if os.path.exists(p) and os.path.isfile(p):
            return p
    try:
        with SessionLocal() as db:
            row = db.execute(
                text("select audio_path from live_calls where conversation_id=:cid order by updated_at desc limit 1"),
                {"cid": call_id},
            ).first()
            if row:
                ap = row[0]
                if ap and os.path.isfile(ap):
                    return ap
    except Exception:
        pass
    return None


async def save_snapshot_from_audio(call_id: str, reason: str = "hangup") -> int:
    path = _find_audio_path(call_id)
    if not path:
        log.info("snapshot_audio: no audio file for call_id=%s", call_id)
        return 0
    try:
        with open(path, "rb") as f:
            wav_bytes = f.read()
        with wave.open(BytesIO(wav_bytes), "rb") as r:
            frames = r.getnframes()
            rate = r.getframerate()
            duration = frames / float(rate or 1)
            log.info("snapshot_audio: path_ok call_id=%s frames=%d rate=%d duration=%.3fs", call_id, frames, rate,
                     duration)
            if duration < MIN_SECONDS:
                log.info("snapshot_audio: too short (%.2fs) -> skip", duration)
                return 0
    except Exception as e:
        log.warning("snapshot_audio: invalid wav for %s: %s", call_id, e)
        return 0
    try:
        bio = BytesIO(wav_bytes)
        bio.seek(0)
        log.info("snapshot_audio: transcribe start call_id=%s model=%s lang=%s", call_id, settings.TRANSCRIBE_MODEL,
                 DEFAULT_LANG)
        tr = openai.audio.transcriptions.create(
            file=("full.wav", bio, "audio/wav"),
            model=settings.TRANSCRIBE_MODEL,
            language=DEFAULT_LANG,
        )
        raw_text = (getattr(tr, "text", "") or "").strip()
        log.info("snapshot_audio: transcribe done call_id=%s chars=%d", call_id, len(raw_text))
        if not raw_text:
            log.info("snapshot_audio: no text -> skip store")
            return 0
        try:
            from ..agents import runner, database_agent
            da_out = await runner.run(database_agent, [{"role": "user", "content": raw_text}])
            anonym = (getattr(da_out, "final_output", "") or "").strip()
        except Exception as e:
            log.warning("snapshot_audio: anonymize failed, using raw: %s", e)
            anonym = ""
        final_text = anonym if (len(anonym) >= max(12, len(raw_text) // 2)) else raw_text
        await anonymize_and_store(final_text, "text/plain", f"snapshot_{reason}.txt", call_id)
        return len(final_text)
    except Exception as e:
        log.exception("snapshot_audio: transcribe/store failed: %s", e)
        return 0
