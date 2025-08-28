# app/routers/telnyx_incoming.py
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Request

from .telnyx_stream import sent_buf
from ..config import settings
from ..logging import setup_logging

log = setup_logging()
router = APIRouter()
answered_sessions = set()

TELNYX_API_KEY = settings.TELNYX_API_KEY
WS_BASE = settings.WS_BASE


def _short(s: str, n: int = 300) -> str: return (s or "")[:n]


QUIET_INCOMING = True


def _log_incoming(et, cid, sess, level="info", msg=""):
    line = f"event={et} cid={cid} sess={sess}"
    if msg:
        line += f" {msg}"
    if level == "debug" or (QUIET_INCOMING and et not in (
            "call.initiated", "call.answered", "call.hangup",
            "streaming.started", "streaming.stopped"
    )):
        log.debug(line)
    else:
        log.info(line)


@router.post("/telnyx/incoming")
async def telnyx_incoming(req: Request):
    body = await req.json()
    data = (body.get("data") or {})
    et = data.get("event_type")
    p = (data.get("payload") or {})
    cid_raw = p.get("call_control_id")
    sess_id = p.get("call_session_id")

    _log_incoming(et, cid_raw, sess_id)

    if et == "call.initiated" and sess_id not in answered_sessions and cid_raw:
        cid = quote(cid_raw, safe="")
        H = {"Authorization": f"Bearer {TELNYX_API_KEY}", "Content-Type": "application/json"}
        payload_answer = {
            "stream_url": f"{WS_BASE}/telnyx/stream?call_id={sess_id}",
            "stream_track": "inbound_track",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=H) as c:
                r1 = await c.post(f"https://api.telnyx.com/v2/calls/{cid}/actions/answer", json=payload_answer)
                if 200 <= r1.status_code < 300:
                    answered_sessions.add(sess_id)
                    log.info("answer+stream %s", r1.status_code)  # kurze Einzeile
                else:
                    # nur Statuscode (Kurzform). Details ggf. auf DEBUG:
                    log.warning("answer+stream non-2xx %s", r1.status_code)
                    if not QUIET_INCOMING:
                        try:
                            log.debug("body=%s", r1.text[:300])
                        except:
                            pass
        except Exception as e:
            log.warning("answer+stream error: %s", e)

    if et == "call.hangup":
        await sent_buf.clear(cid_raw)

    return {"ok": True}
