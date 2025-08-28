# backend/app/routers/telnyx.py
import base64
import io
import os
import uuid
import wave

import httpx
import numpy as np
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from ..logging import setup_logging

log = setup_logging()
router = APIRouter()

TELNYX_API_KEY = os.getenv("TELNYX_API_KEY", "")
PUBLIC_BASE = os.getenv("PUBLIC_BASE", "https://example.com")
WS_BASE = os.getenv("WS_BASE", "wss://example.com")
TRANSCRIBE_URL = os.getenv("TRANSCRIBE_URL", f"{PUBLIC_BASE}/transcribe")
ANALYZE_URL = os.getenv("ANALYZE_URL", f"{PUBLIC_BASE}/analyze_fast")

_rooms = {}


def mu_law_to_linear16(ulaw_bytes: bytes) -> bytes:
    u = np.frombuffer(ulaw_bytes, dtype=np.uint8).astype(np.int16)
    u = ~u
    mag = ((u & 0x0F) << 3) + 0x84
    mag = (mag << ((u & 0x70) >> 4)).astype(np.int32)
    sign = (u & 0x80) != 0
    lin = (mag - 0x84)
    lin = np.where(sign, -lin, lin).astype(np.int16)
    return lin.tobytes()


def pcm16_8k_to_wav_16k_bytes(pcm16_8k: bytes) -> bytes:
    x = np.frombuffer(pcm16_8k, dtype=np.int16).astype(np.float32)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        if x.size == 0:
            w.writeframes(b"")
            return buf.getvalue()
        x_next = np.concatenate([x[1:], x[-1:]])
        mid = ((x + x_next) * 0.5).astype(np.int16)
        up = np.empty(x.size * 2, dtype=np.int16)
        up[0::2] = x.astype(np.int16)
        up[1::2] = mid
        w.writeframes(up.tobytes())
    return buf.getvalue()


async def _broadcast(call_id: str, payload: dict):
    conns = _rooms.get(call_id, {}).get("clients", set())
    dead = []
    for ws in list(conns):
        try:
            await ws.send_json(payload)
        except WebSocketDisconnect:
            dead.append(ws)
        except Exception:
            dead.append(ws)
    for d in dead:
        conns.discard(d)


# oben in der Datei (falls noch nicht da):
import asyncio, json, time
from urllib.parse import quote

answered_sessions = set()


def _short(s: str, n: int = 300) -> str:
    return (s or "")[:n]


@router.post("/telnyx/incoming")
async def telnyx_incoming(req: Request):
    t0 = time.perf_counter()
    body = await req.json()
    data = (body.get("data") or {})
    et = data.get("event_type")
    payload = (data.get("payload") or {})
    cid_raw = payload.get("call_control_id")
    leg_id = payload.get("call_leg_id")
    sess_id = payload.get("call_session_id")

    log.info("📥 recv event=%s cid=%s leg=%s sess=%s", et, cid_raw, leg_id, sess_id)

    if not cid_raw:
        log.warning("⚠️ missing call_control_id on event=%s", et)
        return {"ok": True, "event": et, "note": "no cid"}

    if not sess_id:
        log.warning("⚠️ missing call_session_id on event=%s (will still try)", et)

    # Warnen, falls WSS falsch konfiguriert ist
    if not WS_BASE.startswith("wss://"):
        log.warning("⚠️ WS_BASE not wss:// -> %s", WS_BASE)

    cid_path = quote(cid_raw, safe="")  # v3:… im Pfad escapen
    H = {"Authorization": f"Bearer {TELNYX_API_KEY}", "Content-Type": "application/json"}

    answer_status = None
    answer_body = None

    # -------- 1) Eingehend: sofort (atomar) answer + stream_url --------
    if et == "call.initiated":
        if sess_id in answered_sessions:
            log.info("↩️ already answered for session (sess=%s), skipping", sess_id)
        else:
            try:
                t1 = time.perf_counter()
                async with httpx.AsyncClient(timeout=10.0, headers=H) as c:
                    # Atomar: direkt stream_url beim Answer mitsenden
                    payload_answer = {
                        "stream_url": f"{WS_BASE}/telnyx/stream?call_id={cid_raw}",
                        "stream_track": "inbound_track"
                    }
                    log.info("☎️ answering+stream (cid=%s, sess=%s)…", cid_raw, sess_id)
                    r1 = await c.post(
                        f"https://api.telnyx.com/v2/calls/{cid_path}/actions/answer",
                        json=payload_answer
                    )
                    answer_status, answer_body = r1.status_code, _short(r1.text)
                    dt_api = (time.perf_counter() - t1) * 1000
                    if 200 <= r1.status_code < 300:
                        answered_sessions.add(sess_id or cid_raw)
                        log.info("✅ answer+stream -> %s (%dms) %s",
                                 r1.status_code, dt_api, answer_body)
                    else:
                        # Fehlerdetails klar loggen
                        try:
                            err = r1.json()
                            log.warning("❗ answer+stream non-2xx: %s (%dms) %s",
                                        r1.status_code, dt_api, _short(json.dumps(err)))
                        except Exception:
                            log.warning("❗ answer+stream non-2xx: %s (%dms) %s",
                                        r1.status_code, dt_api, answer_body)
            except Exception as e:
                log.exception("💥 exception during answer+stream: %s", e)

    # -------- 2) Hangup: Ursachen sichtbar machen + Session säubern --------
    if et == "call.hangup":
        # Hangup-Details (sehr wichtig, um 480/487 zu unterscheiden)
        hc = payload.get("hangup_cause")
        sh = payload.get("sip_hangup_cause")
        log.info("🧹 hangup: cause=%s sip=%s (cid=%s sess=%s)",
                 hc, sh, cid_raw, sess_id)
        if sess_id in answered_sessions:
            answered_sessions.discard(sess_id)
            log.info("🧹 removed sess from answered set")
        else:
            log.info("🧹 sess not in answered set (ok)")

    dt = time.perf_counter() - t0
    log.info("🧾 done event=%s cid=%s sess=%s in %.3fs (answer=%s)",
             et, cid_raw, sess_id, dt, answer_status)

    return {
        "ok": True,
        "event": et,
        "call_id": cid_raw,
        "session_id": sess_id,
        "answer_status": answer_status,
        "took": dt,
    }


@router.websocket("/telnyx/stream")
async def telnyx_stream(ws: WebSocket):
    await ws.accept()
    q = dict(p.split("=") for p in (ws.url.query or "").split("&") if p)
    call_id = q.get("call_id") or str(uuid.uuid4())
    room = _rooms.setdefault(call_id, {"buf": bytearray(), "clients": set(), "agg_text": ""})
    throttle = 0

    async def flush_chunk(pcm: bytes):
        wav_bytes = pcm16_8k_to_wav_16k_bytes(pcm)
        files = {"file": ("chunk.wav", wav_bytes, "audio/wav")}
        async with httpx.AsyncClient(timeout=60.0) as c:
            tr = await c.post(TRANSCRIBE_URL, files=files, headers={"x-conversation-id": call_id})
            text = tr.json().get("text", "").strip()
        if not text:
            return
        room["agg_text"] += (" " + text) if room["agg_text"] else text
        msgs = [{"role": "user", "content": room["agg_text"][-4000:]}]
        async with httpx.AsyncClient(timeout=30.0) as c:
            az = await c.post(ANALYZE_URL, json=msgs, headers={"x-conversation-id": call_id})
            data = az.json()
        await _broadcast(call_id, {"type": "update", "call_id": call_id, "text": room["agg_text"],
                                   "trafficLight": data.get("trafficLight", {}),
                                   "suggestions": data.get("suggestions", [])})

    try:
        while True:
            raw = await ws.receive_text()
            evt = json.loads(raw)
            t = evt.get("event")
            if t == "media":
                b = base64.b64decode(evt["payload"]["payload"])
                room["buf"].extend(mu_law_to_linear16(b))
                throttle += 1
                if len(room["buf"]) >= 8000 * 2 or throttle >= 50:
                    chunk = bytes(room["buf"])
                    room["buf"].clear()
                    throttle = 0
                    asyncio.create_task(flush_chunk(chunk))
            elif t == "stop":
                if room["buf"]:
                    chunk = bytes(room["buf"])
                    room["buf"].clear()
                    await flush_chunk(chunk)
                break
    finally:
        await ws.close()


@router.websocket("/ws/client")
async def ws_client(ws: WebSocket):
    await ws.accept()
    q = dict(p.split("=") for p in (ws.url.query or "").split("&") if p)
    call_id = q.get("call_id")
    if not call_id or call_id not in _rooms:
        await ws.close()
        return
    _rooms[call_id]["clients"].add(ws)
    try:
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        pass
    finally:
        _rooms[call_id]["clients"].discard(ws)
