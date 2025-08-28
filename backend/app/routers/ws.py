import json
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
_rooms = defaultdict(set)


@router.websocket("/ws/client")
async def ws_client(ws: WebSocket):
    await ws.accept()
    call_id = ws.query_params.get("call_id") or "default"
    _rooms[call_id].add(ws)
    try:
        while True:
            # optional: pings lesen, aber nichts erwarten
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _rooms[call_id].discard(ws)


async def broadcast(call_id: str, payload: dict):
    dead = []
    for w in list(_rooms[call_id]):
        try:
            await w.send_text(json.dumps(payload))
        except Exception:
            dead.append(w)
    for w in dead:
        _rooms[call_id].discard(w)
