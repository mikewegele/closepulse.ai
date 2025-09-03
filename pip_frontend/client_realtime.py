import asyncio
import base64
import json
import os
import queue
import traceback

import numpy as np
import sounddevice as sd
import websockets

BACKEND_WS = os.getenv("CP_BACKEND_WS", "ws://localhost:8000/realtime/ws")
MIC_NAME = os.getenv("CP_MIC_NAME", "MacBook Pro-Mikrofon")
SPK_NAME = os.getenv("CP_SPK_NAME", "BlackHole 2ch")

SAMPLE_RATE = 16000
BLOCK_SIZE = 1024
Q_MAX = 64


def _find_device_index(name, kind):
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if name.lower() in d["name"].lower():
            if kind == "input" and d["max_input_channels"] > 0:
                return i
            if kind == "output" and d["max_output_channels"] > 0:
                return i
    for i, d in enumerate(devices):
        if kind == "input" and d["max_input_channels"] > 0:
            return i
        if kind == "output" and d["max_output_channels"] > 0:
            return i
    return None


def _pcm16_bytes(frames_float32):
    x = np.clip(frames_float32, -1.0, 1.0)
    x = (x * 32767.0).astype(np.int16)
    return x.tobytes()


async def run():
    in_idx = _find_device_index(MIC_NAME, "input")
    if in_idx is None:
        print(f"[ERROR] Kein Input-Device gefunden (gesucht: '{MIC_NAME}').")
        print(sd.query_devices())
        return

    q_audio = queue.Queue(maxsize=Q_MAX)
    loop = asyncio.get_running_loop()

    async def producer(ws):
        while True:
            b = await loop.run_in_executor(None, q_audio.get)
            enc = base64.b64encode(b).decode("ascii")
            event = {"type": "input_audio_buffer.append", "audio": enc}
            await ws.send(json.dumps(event))

    async def consumer(ws):
        async for message in ws:
            try:
                evt = json.loads(message)
            except Exception:
                continue
            t = evt.get("type")
            if t == "response.text.delta":
                print(evt.get("delta", ""), end="", flush=True)
            elif t == "response.text.done":
                print()
            elif t == "error":
                print("\n[ERROR] ", evt.get("message", "Unbekannter Fehler"))
                details = {k: v for k, v in evt.items() if k not in ("type", "message")}
                if details:
                    print(details)

    async with websockets.connect(BACKEND_WS, ping_interval=20, max_size=16 * 1024 * 1024) as ws:
        def audio_callback(indata, frames, time, status):
            try:
                if status:
                    # Optional: print(status)
                    pass
                mono = indata[:, 0] if indata.ndim > 1 else indata
                b = _pcm16_bytes(mono)
                try:
                    q_audio.put_nowait(b)
                except queue.Full:
                    pass
            except Exception:
                traceback.print_exc()

        istream = sd.InputStream(
            device=in_idx,
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=BLOCK_SIZE,
            callback=audio_callback,
        )

        with istream:
            prod = asyncio.create_task(producer(ws))
            cons = asyncio.create_task(consumer(ws))
            done, pending = await asyncio.wait({prod, cons}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
