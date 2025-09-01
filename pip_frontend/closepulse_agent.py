#!/usr/bin/env python3
"""
ClosePulse Audio-Agent (macOS + Windows)
- Erfasst parallel:
    • MIC  (Mitarbeiter-Mikrofon)
    • SPK  (Kundenspur: macOS via BlackHole 2ch, Windows via WASAPI Loopback)
- Sendet 20ms-Frames (PCM16/16k/mono) an euer Backend:
    ws(s)://<HOST>/local/stream?ext_id=<EXT>&leg=mic|spk

CLI:
  --list-devices           # gibt JSON mit Devices aus (für UI-Auswahl)
  --ws wss://api...        # WS-Base (default: CP_WS_BASE oder wss://api.closepulse192.win)
  --ext EXT_FIXED_ID       # externe Session/Agent-ID
  --mic "Name"             # optional: Mikrofonnamen-Substring
  --spk "Name"             # optional: macOS: BlackHole 2ch; Windows: Headset-Ausgabe-Name
  --rate 16000             # Samplerate (default 16000)
  --frame-ms 20            # Frame-Länge (default 20)
  --rms-gate 0.0075        # Noise-Gate-Schwelle (float, ~-42 dBFS)

ENV (Alternativen zu Flags):
  CP_WS_BASE / CP_EXT_ID / CP_MIC_NAME / CP_SPK_NAME / CP_RATE / CP_FRAME_MS / CP_RMS_GATE
"""

import argparse
import asyncio
import base64
import json
import os
import platform
import signal
import ssl
import sys
import time
from typing import Optional

import certifi
import numpy as np
import sounddevice as sd
import websockets

# Defaults
DEF_WS = os.getenv("CP_WS_BASE", "wss://api.closepulse192.win")
DEF_EXT = os.getenv("CP_EXT_ID", "EXT_FIXED_ID")
DEF_MIC = os.getenv("CP_MIC_NAME")  # None = Default Mic
DEF_SPK = os.getenv("CP_SPK_NAME")  # macOS: "BlackHole 2ch", Windows: Output-Gerätename
DEF_RATE = int(os.getenv("CP_RATE", "16000"))
DEF_MS = int(os.getenv("CP_FRAME_MS", "20"))
DEF_GATE = float(os.getenv("CP_RMS_GATE", "0.0075"))  # ~ -42 dBFS

HEARTBEAT_SEC = 1.0
QUEUE_MAX = 10


def dprint(*a, **k): print(*a, **k, flush=True)


def list_devices_json():
    try:
        devs = sd.query_devices()
        apis = sd.query_hostapis()
    except Exception as e:
        return {"error": str(e)}
    return {"platform": platform.system(), "devices": devs, "hostapis": apis}


def find_input_device_idx(name_substr: Optional[str]) -> Optional[int]:
    devs = sd.query_devices()
    fallback = None
    for i, d in enumerate(devs):
        if d.get("max_input_channels", 0) <= 0:
            continue
        if fallback is None:
            fallback = i
        if name_substr and name_substr.lower() in d["name"].lower():
            return i
    return fallback


def find_wasapi_output_idx(prefer_name: Optional[str]) -> Optional[int]:
    # Windows: wähle ein OUTPUT-Device (wir nutzen es als Input via Loopback)
    try:
        apis = sd.query_hostapis()
        wasapi_idx = next((i for i, h in enumerate(apis) if "wasapi" in h["name"].lower()), None)
    except Exception:
        wasapi_idx = None
    devs = sd.query_devices()
    candidates = [(i, d) for i, d in enumerate(devs) if
                  d.get("max_output_channels", 0) > 0 and (wasapi_idx is None or d.get("hostapi") == wasapi_idx)]
    if prefer_name:
        for i, d in candidates:
            if prefer_name.lower() in d["name"].lower():
                return i
    return candidates[0][0] if candidates else None


def to_pcm16(x: np.ndarray) -> bytes:
    y = x
    if y.ndim == 2 and y.shape[1] > 1:
        y = np.mean(y, axis=1, keepdims=True)
    y = np.clip(y, -1.0, 1.0)
    return (y * 32767.0).astype(np.int16).tobytes()


def rms(x: np.ndarray) -> float:
    if x.size == 0: return 0.0
    return float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))


async def ws_sender(ws_base: str, ext_id: str, leg: str, rate: int, frame_nsamp: int, q: "asyncio.Queue[bytes]"):
    url = f"{ws_base.replace('http', 'ws').rstrip('/')}/local/stream?ext_id={ext_id}&leg={leg}"
    backoff = 1.0
    ssl_ctx = None
    if url.startswith("wss"):
        if os.getenv("CP_WS_INSECURE") == "1":
            ssl_ctx = ssl._create_unverified_context()
        else:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.load_verify_locations(certifi.where())
    while True:
        try:
            async with websockets.connect(url, ssl=ssl_ctx, ping_interval=20, ping_timeout=20, max_queue=8) as ws:
                backoff = 1.0
                last = time.monotonic()
                while True:
                    try:
                        chunk = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_SEC)
                        if chunk is None:
                            return
                        await ws.send(json.dumps({"pcm16": base64.b64encode(chunk).decode("ascii")}))
                        last = time.monotonic()
                    except asyncio.TimeoutError:
                        # Heartbeat: 1 Frame Stille schicken
                        silence = np.zeros((frame_nsamp, 1), dtype=np.float32)
                        await ws.send(json.dumps({"pcm16": base64.b64encode(to_pcm16(silence)).decode("ascii")}))
        except Exception as e:
            dprint(f"[{leg}] ws reconnect in {backoff:.1f}s: {e}", file=sys.stderr)
            await asyncio.sleep(backoff)
            backoff = min(15.0, backoff * 1.7)


class InputLoop:
    def __init__(self, label: str, dev_idx: int, q: "asyncio.Queue[bytes]", rate: int, frame_nsamp: int, gate: float,
                 extra_settings=None):
        self.label = label
        self.q = q
        self.rate = rate
        self.nsamp = frame_nsamp
        self.gate = gate
        self.drop = 0
        kwargs = dict(samplerate=rate, blocksize=frame_nsamp, channels=1, dtype="float32",
                      device=dev_idx, callback=self._cb)
        if extra_settings is not None:
            kwargs["extra_settings"] = extra_settings
        self.stream = sd.InputStream(**kwargs)

    def _cb(self, indata, frames, time_info, status):
        if status:
            dprint(f"[{self.label}] {status}", file=sys.stderr)
        if rms(indata) < self.gate:
            return  # Noise-Gate
        pcm = to_pcm16(indata)
        try:
            self.q.put_nowait(pcm)
        except asyncio.QueueFull:
            self.drop += 1

    def start(self):
        self.stream.start()

    def stop(self):
        self.stream.stop();
        self.stream.close()


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--ws", default=DEF_WS)
    ap.add_argument("--ext", default=DEF_EXT)
    ap.add_argument("--mic", default=DEF_MIC)
    ap.add_argument("--spk", default=DEF_SPK)
    ap.add_argument("--rate", type=int, default=DEF_RATE)
    ap.add_argument("--frame-ms", type=int, default=DEF_MS)
    ap.add_argument("--rms-gate", type=float, default=DEF_GATE)
    return ap.parse_args()


async def run_agent(args):
    # init sounddevice
    try:
        sd.query_devices()
    except Exception as e:
        dprint(
            f"sounddevice init error: {e}\nmacOS: brew install portaudio\nWindows: PortAudio wird mit wheels gebündelt.",
            file=sys.stderr)
        sys.exit(3)

    sysplat = platform.system().lower()
    frame_nsamp = int(args.rate * args.frame_ms / 1000)

    # Geräte ermitteln
    mic_idx = find_input_device_idx(args.mic)
    if mic_idx is None:
        dprint("Kein Mikrofon gefunden. --mic angeben?", file=sys.stderr)
        sys.exit(2)

    extra_spk = None
    if "windows" in sysplat:
        # WASAPI Loopback: wähle OUTPUT-Device, capture via loopback=True
        out_idx = find_wasapi_output_idx(args.spk)
        if out_idx is None:
            dprint("Kein WASAPI-Output-Device gefunden (für Loopback). --spk angeben?", file=sys.stderr)
            sys.exit(2)
        spk_idx = out_idx
        try:
            extra_spk = sd.WasapiSettings(loopback=True)
        except Exception as e:
            dprint(f"WASAPI Loopback nicht verfügbar: {e}", file=sys.stderr);
            sys.exit(2)
    else:
        # macOS/Linux: SPK als Input-Device (macOS: BlackHole 2ch)
        spk_name = args.spk or "BlackHole 2ch"
        spk_idx = find_input_device_idx(spk_name)
        if spk_idx is None:
            dprint(f"Eingabegerät für Kundenspur nicht gefunden (erwartet: '{spk_name}').", file=sys.stderr)
            sys.exit(2)

    # Queues & Streams
    q_mic = asyncio.Queue(maxsize=QUEUE_MAX)
    q_spk = asyncio.Queue(maxsize=QUEUE_MAX)

    mic = InputLoop("mic", mic_idx, q_mic, args.rate, frame_nsamp, args.rms_gate, None)
    spk = InputLoop("spk", spk_idx, q_spk, args.rate, frame_nsamp, args.rms_gate, extra_spk)

    mic.start();
    spk.start()
    dprint(
        f"Agent gestartet: WS={args.ws} EXT={args.ext} mic_idx={mic_idx} spk_idx={spk_idx} rate={args.rate}Hz frame={args.frame_ms}ms gate={args.rms_gate}")

    stop_evt = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, stop_evt.set)
        except NotImplementedError:
            pass

    try:
        await asyncio.gather(
            ws_sender(args.ws, args.ext, "mic", args.rate, frame_nsamp, q_mic),
            ws_sender(args.ws, args.ext, "spk", args.rate, frame_nsamp, q_spk),
            stop_evt.wait(),
        )
    finally:
        mic.stop();
        spk.stop()
        await q_mic.put(None);
        await q_spk.put(None)


if __name__ == "__main__":
    args = parse_args()
    if args.list_devices:
        print(json.dumps(list_devices_json(), indent=2))
        sys.exit(0)
    try:
        asyncio.run(run_agent(args))
    except KeyboardInterrupt:
        pass
