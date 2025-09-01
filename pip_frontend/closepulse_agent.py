# closepulse_agent.py
import asyncio
import json
import os
import time
from collections import deque

import numpy as np
import sounddevice as sd
import websockets

WS_URL = os.getenv("CP_WS_URL", "ws://127.0.0.1:8000/local/stream")
EXT_ID = os.getenv("CP_EXT_ID", "EXT001")
MIC_NAME = os.getenv("CP_MIC_NAME", "MacBook Pro Microphone")
SPK_NAME = os.getenv("CP_SPK_NAME", "BlackHole 2ch")
TARGET_SR = 16000
FRAME_MS = 20
FRAME_SAMPLES = TARGET_SR * FRAME_MS // 1000


def find_device(name, kind):
    for i, d in enumerate(sd.query_devices()):
        if name.lower() in d["name"].lower() and ((kind == "input" and d["max_input_channels"] > 0) or (
                kind == "output" and d["max_output_channels"] > 0)):
            return i, d
    raise RuntimeError(f"device not found: {name} ({kind})")


def to_mono(x):
    if x.ndim == 1: return x
    return np.mean(x, axis=1)


def resample(sig, src_sr, dst_sr):
    if src_sr == dst_sr: return sig
    g = np.gcd(src_sr, dst_sr)
    up = dst_sr // g
    down = src_sr // g
    a = np.repeat(sig, up)
    k = int(np.floor(len(a) / down))
    return a[:k * down:down]


def float_to_pcm16(x):
    y = np.clip(x, -1.0, 1.0)
    return (y * 32767.0).astype(np.int16).tobytes()


async def stream_leg(leg, dev_name):
    dev_idx, dev = find_device(dev_name, "input" if leg == "mic" else "input")
    sr = int(dev["default_samplerate"]) if dev["default_samplerate"] else 48000
    q = asyncio.Queue()
    buf = deque()
    acc = np.empty((0,), dtype=np.float32)

    def cb(indata, frames, time_info, status):
        try:
            q.put_nowait(indata.copy())
        except:
            pass

    with sd.InputStream(device=dev_idx, channels=1 if dev["max_input_channels"] >= 1 else 2, samplerate=sr,
                        dtype="float32", callback=cb):
        uri = f"{WS_URL}?ext_id={EXT_ID}&leg={leg}&sr={TARGET_SR}"
        if os.getenv("CP_WS_INSECURE", "0") == "1" and uri.startswith("wss://"):
            uri = uri.replace("wss://", "ws://")
        async with websockets.connect(
                uri,
                max_size=None,
                additional_headers={"Origin": "http://localhost:3000"}
        ) as ws:
            hello = {"ext_id": EXT_ID, "leg": leg, "ts": time.time(), "sr": TARGET_SR}
            await ws.send(json.dumps(hello))
            while True:
                chunk = await q.get()
                x = to_mono(chunk)
                x = resample(x, sr, TARGET_SR).astype(np.float32)
                if len(x) == 0: continue
                acc = np.concatenate([acc, x])
                while len(acc) >= FRAME_SAMPLES:
                    frame = acc[:FRAME_SAMPLES]
                    acc = acc[FRAME_SAMPLES:]
                    pcm = float_to_pcm16(frame)
                    await ws.send(pcm)


async def main():
    await asyncio.gather(stream_leg("mic", MIC_NAME), stream_leg("spk", SPK_NAME))


if __name__ == "__main__":
    asyncio.run(main())
