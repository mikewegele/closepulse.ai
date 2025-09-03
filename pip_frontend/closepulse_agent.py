import asyncio
import json
import os

import numpy as np
import sounddevice as sd
import websockets

BASE_WS_URL = os.getenv("CP_WS_URL", "ws://127.0.0.1:8000/local/stream?ext_id=DEMO42")
EXT_ID = os.getenv("CP_EXT_ID", "").strip()
MIC_NAME = os.getenv("CP_MIC_NAME", "MacBook Pro-Mikrofon")
SPK_NAME = os.getenv("CP_SPK_NAME", "BlackHole 2ch")
SR = int(os.getenv("CP_SR", "24000"))
FRAME_MS = int(os.getenv("CP_FRAME_MS", "20"))
FRAME_SAMPLES = SR * FRAME_MS // 1000


def ensure_ext_param(url: str, ext_id: str) -> str:
    if "ext_id=" in url or not ext_id:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}ext_id={ext_id}"


WS_URL = ensure_ext_param(BASE_WS_URL, EXT_ID)


def find_device(name, kind):
    for i, d in enumerate(sd.query_devices()):
        if name.lower() in d["name"].lower():
            if kind == "in" and d["max_input_channels"] > 0:
                return i, d
            if kind == "out" and d["max_output_channels"] > 0:
                return i, d
    raise RuntimeError(f"device not found: {name} ({kind})")


def float_to_pcm16(x):
    y = np.clip(x, -1.0, 1.0)
    return (y * 32767.0).astype(np.int16).tobytes()


def pcm16_to_float(b):
    a = np.frombuffer(b, dtype=np.int16).astype(np.float32)
    return a / 32768.0


def resample_linear(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr:
        return x
    n = len(x)
    if n == 0:
        return x
    t_src = np.linspace(0.0, 1.0, num=n, endpoint=False)
    t_dst = np.linspace(0.0, 1.0, num=int(np.floor(n * dst_sr / src_sr)), endpoint=False)
    return np.interp(t_dst, t_src, x).astype(np.float32)


async def main():
    in_idx, in_dev = find_device(MIC_NAME, "in")
    out_idx, out_dev = find_device(SPK_NAME, "out")
    in_sr = int(in_dev["default_samplerate"]) if in_dev["default_samplerate"] else SR
    out_sr = int(out_dev["default_samplerate"]) if out_dev["default_samplerate"] else SR
    print("🎙️ Input :", in_dev["name"], f"(sr={in_sr})")
    print("🔊 Output:", out_dev["name"], f"(sr={out_sr})")
    print("WS_URL =", WS_URL)

    q_in = asyncio.Queue()
    q_out = asyncio.Queue()

    def in_cb(indata, frames, time_info, status):
        try:
            q_in.put_nowait(indata.copy())
        except Exception:
            pass

    def out_cb(outdata, frames, time_info, status):
        try:
            need = frames
            acc = []
            while need > 0:
                try:
                    chunk = q_out.get_nowait()
                except asyncio.QueueEmpty:
                    acc.append(np.zeros((need, 1), dtype=np.float32))
                    break
                x = pcm16_to_float(chunk)
                if x.ndim == 1:
                    x = x[:, None]
                if out_sr != SR:
                    x = resample_linear(x[:, 0], SR, out_sr)[:, None]
                acc.append(x)
                need -= x.shape[0]
            out = np.concatenate(acc, axis=0)
            if out.shape[0] < frames:
                out = np.pad(out, ((0, frames - out.shape[0]), (0, 0)))
            outdata[:] = out[:frames]
        except Exception:
            outdata[:] = 0

    async with websockets.connect(WS_URL, max_size=None) as ws:
        print("[WebSocket] connected")
        with sd.InputStream(device=in_idx, channels=1, samplerate=in_sr, dtype="float32", callback=in_cb), \
                sd.OutputStream(device=out_idx, channels=1, samplerate=out_sr, dtype="float32", callback=out_cb):
            print("[Audio] streams opened\n")

            async def send_audio():
                acc = np.empty((0,), dtype=np.float32)
                while True:
                    chunk = await q_in.get()
                    x = chunk[:, 0].astype(np.float32)
                    if in_sr != SR:
                        x = resample_linear(x, in_sr, SR)
                    acc = np.concatenate([acc, x])
                    while len(acc) >= FRAME_SAMPLES:
                        frame = acc[:FRAME_SAMPLES]
                        acc = acc[FRAME_SAMPLES:]
                        await ws.send(float_to_pcm16(frame))

            async def recv_audio():
                buffer_model = ""
                while True:
                    msg = await ws.recv()
                    if isinstance(msg, bytes):
                        await q_out.put(msg)
                    else:
                        try:
                            ev = json.loads(msg)
                            t = ev.get("type", "")
                            if t == "error":
                                text = ev.get("message", "Unbekannter Fehler")
                                hint = ev.get("hint")
                                print(f"⚠️ {text}")
                                if hint:
                                    print(f" Tipp: {hint}")
                            elif t == "response.text.delta":
                                delta = ev.get("delta", "")
                                buffer_model += delta
                                print("\r🤖", buffer_model, end="", flush=True)
                            elif t == "response.text.done":
                                text = ev.get("text", buffer_model)
                                print("\r🤖", text, flush=True)
                                buffer_model = ""
                            elif t == "input_audio_buffer.speech_started":
                                print("\n🎤 Du sprichst ...")
                            elif t == "input_audio_buffer.speech_stopped":
                                print("🛑 Aufnahme Ende\n")
                        except Exception:
                            pass

            await asyncio.gather(send_audio(), recv_audio())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Ctrl-C] beendet.")
