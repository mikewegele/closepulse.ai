import asyncio
import base64
import json
import os
import ssl

import certifi
import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?model=gpt-realtime"

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")


async def _openai_headers():
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }


async def _send_session_update(ws):
    event = {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "model": "gpt-realtime",
            "output_modalities": ["text"],
            "audio": {
                "input": {
                    "format": "pcm16",
                    "turn_detection": {"type": "semantic_vad", "create_response": True, "interrupt_response": True}
                },
                "output": {
                    "format": "none"
                }
            },
            "instructions": "Antworte knapp auf Deutsch als reiner Text. Jede Antwort ist in sich abgeschlossen."
        }
    }
    await ws.send(json.dumps(event))


@router.websocket("/realtime/ws")
async def realtime_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        async with websockets.connect(
                OPENAI_REALTIME_URL,
                additional_headers=await _openai_headers(),
                ping_interval=20,
                max_size=16 * 1024 * 1024,
                ssl=ssl_ctx,
        ) as upstream:
            # await _send_session_update(upstream)

            async def client_to_openai():
                try:
                    while True:
                        msg = await websocket.receive()
                        if "bytes" in msg and msg["bytes"] is not None:
                            b = msg["bytes"]
                            enc = base64.b64encode(b).decode("ascii")
                            event = {"type": "input_audio_buffer.append", "audio": enc}
                            await upstream.send(json.dumps(event))
                        elif "text" in msg and msg["text"] is not None:
                            try:
                                payload = json.loads(msg["text"])
                                t = payload.get("type")
                                if t in {"input_audio_buffer.append", "input_audio_buffer.commit", "response.create",
                                         "session.update", "conversation.item.create", "input_audio_buffer.clear"}:
                                    await upstream.send(json.dumps(payload))
                                else:
                                    event = {
                                        "type": "conversation.item.create",
                                        "item": {
                                            "type": "message",
                                            "role": "user",
                                            "content": [{"type": "input_text", "text": msg["text"]}]
                                        }
                                    }
                                    await upstream.send(json.dumps(event))
                                    await upstream.send(
                                        json.dumps({"type": "response.create", "response": {"modalities": ["text"]}}))
                            except json.JSONDecodeError:
                                event = {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "message",
                                        "role": "user",
                                        "content": [{"type": "input_text", "text": msg["text"]}]
                                    }
                                }
                                await upstream.send(json.dumps(event))
                                await upstream.send(
                                    json.dumps({"type": "response.create", "response": {"modalities": ["text"]}}))
                except WebSocketDisconnect:
                    try:
                        await upstream.close()
                    except:
                        pass

            async def openai_to_client():
                async for message in upstream:
                    try:
                        server_event = json.loads(message)
                    except:
                        continue
                    et = server_event.get("type")
                    if et in {"response.text.delta", "response.text.done", "response.created", "response.done",
                              "session.created", "session.updated", "input_audio_buffer.speech_started",
                              "input_audio_buffer.speech_stopped", "error"}:
                        await websocket.send_text(json.dumps(server_event))

            t1 = asyncio.create_task(client_to_openai())
            t2 = asyncio.create_task(openai_to_client())
            await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        finally:
            await websocket.close()
