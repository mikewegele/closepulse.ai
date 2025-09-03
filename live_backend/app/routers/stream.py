# app/routers/stream.py
import asyncio
import base64
import json
import os
import ssl
from typing import Optional

import certifi
import numpy as np
import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

router = APIRouter()

OAI_URL = os.getenv("CP_OAI_REALTIME_URL", "wss://api.openai.com/v1/realtime")
OAI_MODEL = os.getenv("CP_OAI_REALTIME_MODEL", "gpt-4o-realtime-preview")
OAI_VOICE = os.getenv("CP_OAI_VOICE", "alloy")
IN_FMT = os.getenv("CP_INPUT_AUDIO_FORMAT", "pcm16")
OUT_FMT = os.getenv("CP_OUTPUT_AUDIO_FORMAT", "pcm16")
TARGET_SR = int(os.getenv("CP_TARGET_SR", "24000"))
SIL_MS = int(os.getenv("CP_VAD_SIL_MS", "600"))
PAD_MS = int(os.getenv("CP_VAD_PAD_MS", "250"))
CREATE_RESP = os.getenv("CP_VAD_CREATE_RESPONSE", "1") == "1"
SYS_INSTR = os.getenv("CP_SYSTEM_INSTRUCTIONS", "")


def resample_linear(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr:
        return x
    n = len(x)
    if n == 0:
        return x
    t_src = np.linspace(0.0, 1.0, num=n, endpoint=False)
    t_dst = np.linspace(0.0, 1.0, num=int(np.floor(n * dst_sr / src_sr)), endpoint=False)
    return np.interp(t_dst, t_src, x).astype(np.float32)


def pcm16_bytes_to_float32(b: bytes) -> np.ndarray:
    a = np.frombuffer(b, dtype=np.int16).astype(np.float32)
    return a / 32768.0


def float32_to_pcm16_bytes(x: np.ndarray) -> bytes:
    y = np.clip(x, -1.0, 1.0)
    return (y * 32767.0).astype(np.int16).tobytes()


async def connect_openai():
    url = f"{OAI_URL}?model={OAI_MODEL}"
    headers = [
        ("Authorization", f"Bearer {os.getenv('OPENAI_API_KEY', '')}"),
        ("OpenAI-Beta", "realtime=v1"),
    ]
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    return await websockets.connect(url, additional_headers=headers, max_size=None, ssl=ssl_ctx)


@router.websocket("/stream")
async def stream(ws: WebSocket, ext_id: str = "EXT001", leg: Optional[str] = Query(default=None), sr: int = TARGET_SR):
    await ws.accept()
    try:
        oai = await connect_openai()
    except Exception as e:
        await ws.send_text(json.dumps({
            "type": "error",
            "source": "openai",
            "message": f"Upstream connect failed: {type(e).__name__}: {e}",
            "hint": "Prüfe OPENAI_API_KEY und CP_OAI_REALTIME_MODEL.",
        }))
        await ws.close()
        return

    await oai.send(json.dumps({
        "type": "session.update",
        "session": {
            "type": "realtime",
            "model": OAI_MODEL,
            "output_modalities": ["audio", "text"],
            "audio": {
                "input": {
                    "format": IN_FMT,
                    "turn_detection": {"type": "semantic_vad", "create_response": CREATE_RESP,
                                       "silence_duration_ms": SIL_MS, "prefix_padding_ms": PAD_MS}
                },
                "output": {
                    "format": OUT_FMT,
                    "voice": OAI_VOICE,
                }
            },
            "instructions": SYS_INSTR,
        }
    }))

    async def safe_send_oai(obj: dict):
        try:
            await oai.send(json.dumps(obj))
        except Exception:
            pass

    async def pump_client_to_oai():
        try:
            while True:
                msg = await ws.receive()
                if "bytes" in msg and msg["bytes"]:
                    b = msg["bytes"]
                    if sr != TARGET_SR:
                        x = pcm16_bytes_to_float32(b)
                        x = resample_linear(x, sr, TARGET_SR)
                        b = float32_to_pcm16_bytes(x)
                    await safe_send_oai(
                        {"type": "input_audio_buffer.append", "audio": base64.b64encode(b).decode("ascii")})
                elif "text" in msg and msg["text"]:
                    try:
                        obj = json.loads(msg["text"])
                        await safe_send_oai(obj)
                    except Exception:
                        pass
                elif msg.get("type") == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        try:
            await oai.close()
        except Exception:
            pass

    async def pump_oai_to_client():
        try:
            async for raw in oai:
                try:
                    ev = json.loads(raw)
                except Exception:
                    continue
                t = ev.get("type", "")
                if t == "response.audio.delta":
                    try:
                        await ws.send_bytes(base64.b64decode(ev.get("delta", "")))
                    except Exception:
                        pass
                    continue
                if t == "response.audio.done":
                    try:
                        await ws.send_text("AUDIO_DONE")
                    except Exception:
                        pass
                    continue
                if t == "input_audio_buffer.speech_stopped":
                    try:
                        await ws.send_text(json.dumps(ev))
                    except Exception:
                        pass
                    if not CREATE_RESP:
                        await safe_send_oai({"type": "input_audio_buffer.commit"})
                        await safe_send_oai({"type": "response.create", "response": {"modalities": ["audio", "text"]}})
                    continue
                try:
                    await ws.send_text(json.dumps(ev))
                except Exception:
                    pass
        except Exception as e:
            try:
                await ws.send_text(
                    json.dumps({"type": "error", "source": "openai-stream", "message": f"{type(e).__name__}: {e}"}))
            except Exception:
                pass
        try:
            await ws.close()
        except Exception:
            pass

    t1 = asyncio.create_task(pump_client_to_oai())
    t2 = asyncio.create_task(pump_oai_to_client())
    await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
    for t in (t1, t2):
        if not t.done():
            t.cancel()
