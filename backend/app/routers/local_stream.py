# app/routes/local_stream.py
from __future__ import annotations

import base64
import json
import os
import time
import wave

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings
from ..logging import setup_logging

log = setup_logging()
router = APIRouter()

AUDIO_DIR = getattr(settings, "AUDIO_DIR", "./recordings")
os.makedirs(AUDIO_DIR, exist_ok=True)

SAMPLE_RATE = 16000  # erwartet PCM16 @ 16k mono
SAMPLE_WIDTH = 2
CHANNELS = 1


@router.websocket("/local/stream")
async def local_stream(ws: WebSocket):
    """
    Erwartet Textframes (JSON) mit Feld "pcm16" (base64-kodierte Bytes, 16-bit, mono, 16kHz).
    Query-Parameter:
      - ext_id: externe ID (Pfadpräfix)
      - leg: "mic" oder "spk" (Dateiname-Suffix)
    Schreibt fortlaufend in eine WAV-Datei bis die WS-Verbindung beendet wird.
    """
    await ws.accept()

    ext_id = ws.query_params.get("ext_id") or "EXT"
    leg = (ws.query_params.get("leg") or "mic").lower().strip()
    if leg not in ("mic", "spk"):
        leg = "mic"

    ts = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(AUDIO_DIR, f"{ext_id}-{ts}-{leg}.wav")

    # WAV anlegen
    try:
        w = wave.open(path, "wb")
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(SAMPLE_RATE)
    except Exception as e:
        log.exception("local_stream: cannot open wav path=%s err=%s", path, e)
        await ws.close()
        return

    total_bytes = 0
    start_t = time.monotonic()
    log.info("local_stream: START ext=%s leg=%s -> %s", ext_id, leg, path)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                obj = json.loads(raw)
                b64 = obj.get("pcm16")
                if not b64:
                    continue
                chunk = base64.b64decode(b64)
                # nur gültige 16-bit Mono-Chunks
                if not chunk or (len(chunk) & 1):
                    continue
                w.writeframes(chunk)
                total_bytes += len(chunk)
            except Exception:
                # ungültiges JSON/Chunk -> ignorieren
                continue
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.exception("local_stream: error ext=%s leg=%s err=%s", ext_id, leg, e)
    finally:
        try:
            w.close()
        except Exception:
            pass
        try:
            await ws.close()
        except Exception:
            pass

        dur_s = (time.monotonic() - start_t)
        # WAV-Datenbereich grob: total_bytes (wir haben nur Daten geschrieben)
        log.info("local_stream: END ext=%s leg=%s bytes=%d approx_dur=%.2fs file=%s",
                 ext_id, leg, total_bytes, total_bytes / (SAMPLE_RATE * SAMPLE_WIDTH) if total_bytes else 0.0, path)
