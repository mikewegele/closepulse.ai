import time
import wave
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .analyze import analyze_fast
from .transcribe import transcribe_by_ext
from ..vad import SilenceDetector

router = APIRouter()
detectors = {}
recordings_dir = Path("recordings")
recordings_dir.mkdir(exist_ok=True)


@router.websocket("/local/stream")
async def local_stream(ws: WebSocket, ext_id: str, leg: str, sr: int = 16000):
    await ws.accept()
    if ext_id not in detectors:
        detectors[ext_id] = SilenceDetector(silence_sec=1.0)
    detector = detectors[ext_id]

    ts = time.strftime("%Y%m%d-%H%M%S")
    filename = recordings_dir / f"{ext_id}-{ts}-{leg}.wav"
    wf = wave.open(str(filename), "wb")
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sr)

    try:
        msg = await ws.receive()
        if "bytes" in msg and msg["bytes"]:
            frame = msg["bytes"]
            wf.writeframes(frame)
            if leg == "spk" and detector.update(frame):
                text = await transcribe_by_ext(ext_id)
                if text:
                    res = await analyze_fast([{"role": "user", "content": text}])
                    print(f"[{ext_id}] Pause erkannt → Vorschläge:", res)

        while True:
            msg = await ws.receive()
            if "bytes" in msg and msg["bytes"]:
                frame = msg["bytes"]
                wf.writeframes(frame)
                if leg == "spk" and detector.update(frame):
                    text = await transcribe_by_ext(ext_id)
                    if text:
                        res = await analyze_fast([{"role": "user", "content": text}])
                        print(f"[{ext_id}] Pause erkannt → Vorschläge:", res)
            elif "text" in msg and msg["text"]:
                pass
            elif msg.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        try:
            wf.close()
        except:
            pass
        print(f"Stream {ext_id}/{leg} beendet")
