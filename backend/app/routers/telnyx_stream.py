# app/routers/telnyx_stream.py
from __future__ import annotations

import asyncio
import audioop
import base64
import httpx
import io
import json
import time
import wave

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings
from ..logging import setup_logging
from ..services.audio_sink import audio_sinks
from ..state.live_store import live_store

log = setup_logging()
router = APIRouter()

TRANSCRIBE_URL = f"{settings.PUBLIC_BASE}/transcribe?store=0"
CHUNK_SEC = 1.0
VERBOSE_WS = False


def mulaw_to_lin16(mu: bytes) -> bytes:
    if not mu:
        return b""
    return audioop.ulaw2lin(mu, 2)


async def flush_and_transcribe(call_id: str, pcm8k: bytes) -> None:
    if not pcm8k:
        return
    try:
        new, _ = audioop.ratecv(pcm8k, 2, 1, 8000, 16000, None)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(new)
        files = {"file": ("chunk.wav", buf.getvalue(), "audio/wav")}
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.post(TRANSCRIBE_URL, files=files, headers={"x-conversation-id": call_id})
        j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        text = (j.get("text") or "").strip()
        if text:
            live_store.add_text(call_id, text)
    except Exception:
        pass


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

    buf = bytearray()
    last_flush = time.perf_counter()

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
                    sink.append_pcm8k_lin16(pcm8k)
                    buf.extend(pcm8k)
                if (time.perf_counter() - last_flush) >= CHUNK_SEC and buf:
                    chunk = bytes(buf)
                    buf.clear()
                    last_flush = time.perf_counter()
                    asyncio.create_task(flush_and_transcribe(call_id, chunk))
                continue

            if et == "stop":
                if buf:
                    try:
                        await flush_and_transcribe(call_id, bytes(buf))
                    except Exception:
                        pass
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
