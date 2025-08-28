# app/routers/telnyx_stream.py
import asyncio
import base64
import io
import json
import time
import wave

import audioop
import httpx
from fastapi import APIRouter, WebSocket
from models import TranscriptChunk

from ..config import settings
from ..logging import setup_logging
from ..services.anonymize import anonymize_and_store
from ..services.paragraph_buffer import ParagraphBuffer
from ..services.sentence_buffer import SentenceBuffer

log = setup_logging()
router = APIRouter()
TRANSCRIBE_URL = f"{settings.PUBLIC_BASE}/transcribe"  # du hast /transcribe schon
CHUNK_SEC = 1.0  # ~1s Puffer

sent_buf = SentenceBuffer(
    idle_flush_sec=2.0,
    min_sentence_len=5,
    min_flush_chars=60,  # aggressiver: lange Sätze bevorzugen
    min_flush_words=4,
    short_join_max_wait=4.0,
    dedup_ratio=0.92,
)

para_buf = ParagraphBuffer(
    target_chars=200,  # << hier Stellschraube
    max_sents=4,
    idle_flush_sec=6.0,
    dedup_ratio=0.90,
)


async def _persist_paragraph(call_id: str, paragraph: str):
    await anonymize_and_store(paragraph, "text/plain", "stt.txt", call_id)


async def _store_sentence(call_id: str, sentence: str):
    await para_buf.add(call_id, sentence, _persist_paragraph)


def mulaw_to_lin16(mu: bytes) -> bytes:
    # 8kHz PCMU → 16-bit PCM @8k
    return audioop.ulaw2lin(mu, 2)  # width=2


def pcm8k_to_wav16k_bytes(pcm8k: bytes) -> bytes:
    # auf 16k resamplen (mono, 16-bit)
    new, _ = audioop.ratecv(pcm8k, 2, 1, 8000, 16000, None)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1);
        w.setsampwidth(2);
        w.setframerate(16000)
        w.writeframes(new)
    return buf.getvalue()


async def flush_and_transcribe(
        call_id: str,
        pcm8k: bytes,
        t0_ms: int | None = None,
        t1_ms: int | None = None,
):
    if not pcm8k:
        return
    wav = pcm8k_to_wav16k_bytes(pcm8k)
    files = {"file": ("chunk.wav", wav, "audio/wav")}
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.post(TRANSCRIBE_URL, files=files, headers={"x-conversation-id": call_id})
        text = (r.json().get("text") or "").strip()
    if text:
        await sent_buf.add(call_id, text, _store_sentence)


VERBOSE_WS = False  # bei Bedarf True


def _get_audio_b64(evt: dict) -> str | None:
    # Telnyx schickt meist: {"event":"media","payload":{"payload":"<b64>", ...}}
    pl = evt.get("payload") or evt.get("media") or {}
    return pl.get("payload") or pl.get("data")  # tolerant


@router.websocket("/telnyx/stream")
async def telnyx_stream(ws: WebSocket):
    await ws.accept()
    call_id = ws.query_params.get("call_id") or "unknown"  # => session_id
    buf = bytearray()
    last_flush = time.perf_counter()
    try:
        while True:
            raw = await ws.receive_text()
            evt = json.loads(raw)
            et = (evt.get("event") or "").lower()
            if et == "media":
                mu = base64.b64decode(_get_audio_b64(evt) or b"")
                pcm8k = mulaw_to_lin16(mu)
                buf.extend(pcm8k)
                if (time.perf_counter() - last_flush) >= CHUNK_SEC:
                    chunk = bytes(buf);
                    buf.clear();
                    last_flush = time.perf_counter()
                    asyncio.create_task(flush_and_transcribe(call_id, chunk))
            elif et == "stop":
                if buf:
                    await flush_and_transcribe(call_id, bytes(buf))
                await sent_buf.force_flush(call_id, _store_sentence)
                await para_buf.force_flush(call_id, _persist_paragraph)
                break

    finally:
        await ws.close()
        await sent_buf.clear(call_id)
        await para_buf.clear(call_id)
