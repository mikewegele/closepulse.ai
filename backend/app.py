# backend/app.py (Auszug)
import asyncio
import json
import logging
import os
import time
from typing import Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.suggestions import make_suggestions

logging.basicConfig(level=os.environ.get("BACKEND_LOG_LEVEL", "INFO"))
log = logging.getLogger("cp.backend")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

subs: Dict[str, Set[WebSocket]] = {}
locks: Dict[str, asyncio.Lock] = {}


def _room(ext: str) -> Set[WebSocket]:
    return subs.setdefault(ext, set())


def _lock(ext: str) -> asyncio.Lock:
    if ext not in locks:
        locks[ext] = asyncio.Lock()
    return locks[ext]


async def _broadcast(ext: str, payload: dict):
    dead = []
    for ws in list(_room(ext)):
        try:
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
        except:
            dead.append(ws)
    for ws in dead:
        _room(ext).discard(ws)


@app.get("/")
def health():
    return {"ok": True}


@app.websocket("/ws/transcript")
async def ws_transcript(ws: WebSocket):
    ext = ws.query_params.get("ext") or "default"
    await ws.accept()
    _room(ext).add(ws)  # <— HINZUFÜGEN!
    log.info("[B] transcript:connect ext=%s", ext)
    try:
        while True:
            raw = await ws.receive_text()
            log.info("[B] transcript:receive raw=%s", raw)
            try:
                data = json.loads(raw)
            except:
                continue

            role = data.get("role")
            text = (data.get("text") or "").strip()

            if role == "agent" and text:
                t0 = time.perf_counter()
                async with _lock(ext):
                    sug = await make_suggestions(text)
                dt = time.perf_counter() - t0

                snip = (text[:80] + ("…" if len(text) > 80 else "")).replace("\n", " ")
                log.info('[B] suggest ext=%s dt_ms=%d text="%s"', ext, int(dt * 1000), snip)
                await _broadcast(ext, sug)
    except WebSocketDisconnect:
        log.info("[B] transcript:disconnect ext=%s", ext)
    finally:
        _room(ext).discard(ws)  # <— AUFRÄUMEN!
