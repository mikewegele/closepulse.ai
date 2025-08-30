from __future__ import annotations

import base64
import json

import audioop
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings
from ..db import SessionLocal
from ..logging import setup_logging
from ..services.audio_sink import audio_sinks
from ..services.live_audio import append_audio_chunk  # hängt an eine WAV pro Call
from ..state.live_store import live_store

log = setup_logging()
router = APIRouter()


def mulaw_to_lin16(mu: bytes) -> bytes:
    if not mu:
        return b""
    return audioop.ulaw2lin(mu, 2)  # 16-bit PCM @ 8k


def _get_audio_b64(evt: dict) -> str | None:
    pl = evt.get("payload") or evt.get("media") or {}
    return pl.get("payload") or pl.get("data")


async def close_audio_for_session(sess_key: str):
    audio_sinks.close(sess_key)


@router.websocket("/telnyx/stream")
async def telnyx_stream(ws: WebSocket):
    await ws.accept()
    call_id = ws.query_params.get("call_id") or "unknown"
    ext_id = ws.query_params.get("ext_id") or settings.EXTERNAL_CALL_ID
    sink = audio_sinks.open(call_id, settings.AUDIO_DIR, ext_id)
    await live_store.set_ext_id(call_id, ext_id)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                evt = json.loads(raw)
            except Exception:
                continue
            et = (evt.get("event") or evt.get("type") or "").lower()

            if et == "media":
                b64 = _get_audio_b64(evt)
                if not b64:
                    continue
                mu = base64.b64decode(b64)
                pcm8k = mulaw_to_lin16(mu)
                if pcm8k:
                    # 1) immer Audio-Append (eine Datei pro Call)
                    sink.append_pcm8k_lin16(pcm8k)
                    try:
                        async with SessionLocal() as db:
                            await append_audio_chunk(db, call_id, ext_id, pcm8k, meta={"source": "telnyx"})
                    except Exception:
                        pass
                continue

            if et == "stop":
                break

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
        await close_audio_for_session(call_id)
