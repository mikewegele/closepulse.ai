from urllib.parse import quote

import httpx
from fastapi import APIRouter, Request

from .telnyx_stream import close_audio_for_session
from ..config import settings
from ..logging import setup_logging
from ..services.snapshot_audio import save_snapshot_from_audio
from ..state.live_store import live_store

log = setup_logging()
router = APIRouter()
answered_sessions = set()

TELNYX_API_KEY = settings.TELNYX_API_KEY
WS_BASE = settings.WS_BASE


@router.post("/telnyx/incoming")
async def telnyx_incoming(req: Request):
    body = await req.json()
    data = body.get("data") or {}
    et = data.get("event_type")
    p = data.get("payload") or {}
    cid_raw = p.get("call_control_id")
    sess_id = p.get("call_session_id")

    if et == "call.initiated" and sess_id and sess_id not in answered_sessions:
        H = {"Authorization": f"Bearer {TELNYX_API_KEY}", "Content-Type": "application/json"}
        ext_id = settings.EXTERNAL_CALL_ID
        payload_answer = {
            "stream_url": f"{WS_BASE}/telnyx/stream?call_id={sess_id}&ext_id={quote(ext_id, safe='')}",
            "stream_track": "inbound_track",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=H) as c:
                cid_path = quote(cid_raw or "", safe="")
                r1 = await c.post(f"https://api.telnyx.com/v2/calls/{cid_path}/actions/answer", json=payload_answer)
                if 200 <= r1.status_code < 300:
                    answered_sessions.add(sess_id)
                    await live_store.set_ext_id(sess_id, ext_id)
        except Exception:
            pass

    if et == "call.hangup" and sess_id:
        try:
            # WICHTIG: zuerst Audio schließen/flushen
            await close_audio_for_session(sess_id)
            await live_store.mark_ended(sess_id)

            # Danach komplette WAV transkribieren & speichern
            await save_snapshot_from_audio(sess_id, reason="hangup")
        except Exception:
            pass
        finally:
            live_store.clear(sess_id)
            answered_sessions.discard(sess_id)

    return {"ok": True}
