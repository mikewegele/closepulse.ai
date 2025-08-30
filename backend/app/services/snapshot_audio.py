# app/services/snapshot_audio.py
import os
import wave
from io import BytesIO
from typing import Optional

import openai

from ..config import settings
from ..logging import setup_logging
from ..services.anonymize import anonymize_and_store

log = setup_logging()
AUDIO_DIR = getattr(settings, "AUDIO_DIR", "./audio")
MIN_SECONDS = float(getattr(settings, "FINAL_MIN_SECONDS", 1.0))  # mind. 1.0 s
TARGET_RATE = 16000


def _find_audio_path(call_id: str) -> Optional[str]:
    p = os.path.join(AUDIO_DIR, f"{call_id}.wav")
    return p if os.path.exists(p) else None


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
            duration = frames / float(rate or TARGET_RATE)
            if duration < MIN_SECONDS:
                log.info("snapshot_audio: too short (%.2fs) -> skip", duration)
                return 0
    except Exception as e:
        log.warning("snapshot_audio: invalid wav for %s: %s", call_id, e)
        return 0

    try:
        bio = BytesIO(wav_bytes);
        bio.seek(0)
        # Sprache explizit setzen, falls du DE willst:
        lang = getattr(settings, "TRANSCRIBE_LANG", None) or "de"
        tr = openai.audio.transcriptions.create(
            file=("full.wav", bio, "audio/wav"),
            model=settings.TRANSCRIBE_MODEL,  # z.B. "whisper-1" oder "gpt-4o-mini-transcribe"
            language=lang,
        )
        raw_text = (getattr(tr, "text", "") or "").strip()
        if not raw_text:
            log.info("snapshot_audio: no text -> skip store")
            return 0

        # Anonymisieren + robustes Fallback (sicherstellen, dass Inhalt nicht zu kurz wird)
        try:
            # anonymize_and_store speichert selbst; wir wollen aber den Text prüfen:
            # -> wir rufen anonymizer separat und prüfen Länge
            from ..agents import runner, database_agent
            da_out = await runner.run(database_agent, [{"role": "user", "content": raw_text}])
            anonym = (getattr(da_out, "final_output", "") or "").strip()
        except Exception as e:
            log.warning("snapshot_audio: anonymize failed, using raw: %s", e)
            anonym = ""

        # Fallback-Regel: nimm RAW, wenn anonymisiert zu kurz ist (< 50% der Länge oder < 12 Zeichen)
        final_text = anonym if (len(anonym) >= max(12, len(raw_text) // 2)) else raw_text

        await anonymize_and_store(final_text, "text/plain", f"snapshot_{reason}.txt", call_id)
        return len(final_text)
    except Exception as e:
        log.exception("snapshot_audio: transcribe/store failed: %s", e)
        return 0
