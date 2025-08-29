import time
from io import BytesIO
from typing import Optional

import openai
from fastapi import APIRouter, UploadFile, File, HTTPException, Header, BackgroundTasks, Query

from ..config import settings
from ..logging import setup_logging
from ..services.anonymize import anonymize_and_store  # bleibt importiert, wird hier aber nicht genutzt
from ..utils import safe_mime_from_upload

log = setup_logging()
router = APIRouter()


@router.post("/transcribe")
async def transcribe(
        file: UploadFile = File(...),
        x_conversation_id: Optional[str] = Header(default=None, convert_underscores=False),
        background_tasks: BackgroundTasks = None,
        store: bool = Query(default=False),  # ⚠️ Default jetzt FALSE
):
    """
    STT-only Endpoint.
    - Speichert NICHT mehr automatisch.
    - Rückgabe nur Text + Dauer.
    - Speichern passiert ausschließlich per Snapshot-Service (💡/Hangup).
    """
    t0 = time.perf_counter()
    try:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty audio payload")

        mime = safe_mime_from_upload(file)
        name = file.filename or ("audio.webm" if "webm" in mime else "audio.wav")
        wav_io = BytesIO(raw)

        tr = openai.audio.transcriptions.create(
            file=(name, wav_io, mime),
            model=settings.TRANSCRIBE_MODEL,
            language=settings.TRANSCRIBE_LANG,
        )
        text = (getattr(tr, "text", "") or "").strip()
        dt = time.perf_counter() - t0

        # Nur noch STT – kein Auto-Store mehr.
        # Harte Bremse über STORE_MODE: selbst wenn ?store=1 übergeben wird,
        # speichern wir NUR im Modus "always".
        mode = (getattr(settings, "STORE_MODE", "on_demand") or "on_demand").lower()
        can_store = bool(store) and mode == "always"

        log.info("/transcribe %.3fs store=%s mode=%s (auto-save %s)",
                 dt, store, mode, "ENABLED" if can_store else "DISABLED")

        if text and can_store:
            # Normalfall bei uns: can_store == False → nix speichern
            if background_tasks is not None:
                background_tasks.add_task(anonymize_and_store, text, mime, name, x_conversation_id)
            else:
                import asyncio
                asyncio.create_task(anonymize_and_store(text, mime, name, x_conversation_id))

        return {"text": text, "duration": dt, "conversation_id": x_conversation_id}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("transcribe failed: %s", e)
        raise HTTPException(status_code=500, detail=f"transcribe failed: {e}") from e
