#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
closepulse_agent.py — STT-Only Agent
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import signal
import ssl
import sys
from typing import Optional, Tuple

import certifi
import sounddevice as sd
import websockets
from dotenv import load_dotenv

# --- Setup & Config ----------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=os.environ.get("CP_LOG", "INFO"),
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
)
log = logging.getLogger("cp.agent.stt")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
TRANSCRIBE_MODEL = os.environ.get("TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
LANG_DEFAULT = os.environ.get("CP_LANG", "de")

RATE = int(os.environ.get("CP_RATE_IN", "16000"))
CHUNK_MS = 20
CHUNK = int(RATE * CHUNK_MS / 1000)

RT_URL = "wss://api.openai.com/v1/realtime?intent=transcription"

# global Stop-Event
STOP_EVT = asyncio.Event()


def _ssl_ctx(url: str | None):
    if url and url.startswith("wss://"):
        return ssl.create_default_context(cafile=certifi.where())
    return None


def _rt_headers():
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY fehlt")
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1",
    }


# --- Audio Helpers -----------------------------------------------------------------

def list_devices():
    devs = sd.query_devices()
    ins = [d["name"] for d in devs if d.get("max_input_channels", 0) > 0]
    outs = [d["name"] for d in devs if d.get("max_output_channels", 0) > 0]
    print(json.dumps({"inputs": ins, "outputs": outs}, ensure_ascii=False))


def _find_input_device(name: Optional[str]) -> Optional[int]:
    if not name:
        return None
    name_low = name.lower()
    for i, d in enumerate(sd.query_devices()):
        if d.get("max_input_channels", 0) > 0 and name_low in (d.get("name", "").lower()):
            return i
    return None


def make_reader(name: Optional[str]) -> Tuple[asyncio.Queue, sd.RawInputStream]:
    idx = _find_input_device(name)
    q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)

    def cb(indata, frames, t, status):
        try:
            q.put_nowait(bytes(indata))
        except asyncio.QueueFull:
            pass

    stream = sd.RawInputStream(
        samplerate=RATE,
        channels=1,
        dtype="int16",
        blocksize=CHUNK,
        device=idx,
        callback=cb,
    )
    return q, stream


# --- Realtime (OpenAI) --------------------------------------------------------------

async def open_transcription_session(noise_type: str, lang: str):
    try:
        ws = await websockets.connect(
            RT_URL,
            additional_headers=_rt_headers(),
            ssl=_ssl_ctx(RT_URL),
            ping_interval=20,
            max_size=16_000_000,
        )
    except Exception as e:
        log.error(f"[A] realtime connect failed: {e}")
        return None

    try:
        try:
            raw0 = await asyncio.wait_for(ws.recv(), timeout=5)
            _evt0 = json.loads(raw0)
            log.debug(f"[A] first evt: {_evt0.get('type')}")
        except Exception:
            pass

        await ws.send(json.dumps({
            "type": "transcription_session.update",
            "session": {
                "input_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": TRANSCRIBE_MODEL,
                    "language": lang,
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 700
                },
                "input_audio_noise_reduction": {"type": noise_type},
            }
        }))

        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            evt = json.loads(raw)
            if evt.get("type") == "transcription_session.updated":
                break
            if evt.get("type") == "error":
                log.error(f"[A] realtime error: {evt}")
                await ws.close()
                return None

    except Exception as e:
        log.error(f"transcription_session.update failed: {e}")
        try:
            await ws.close()
        except Exception:
            pass
        return None

    return ws


async def pump_audio(q: asyncio.Queue, ws, stop_evt: asyncio.Event):
    while not stop_evt.is_set():
        try:
            buf = await asyncio.wait_for(q.get(), timeout=0.25)
        except asyncio.TimeoutError:
            continue
        if not buf or ws is None or getattr(ws, "closed", False):
            continue
        try:
            await ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(buf).decode("ascii")
            }))
        except Exception:
            await asyncio.sleep(0.05)


async def consume_transcripts(role: str, ws, backend_ws, stop_evt: asyncio.Event):
    if ws is None:
        return
    try:
        async for raw in ws:
            if stop_evt.is_set():
                break
            evt = json.loads(raw)
            if evt.get("type") == "conversation.item.input_audio_transcription.completed":
                transcript = (evt.get("transcript") or "").strip()
                if transcript:
                    print(f'[A] {role}: "{transcript}"')
                    if backend_ws:
                        try:
                            await backend_ws.send(json.dumps({"role": role, "text": transcript}))
                        except Exception:
                            pass
    except Exception as e:
        log.warning(f"[A] consume err: {e}")


# --- Backend WS --------------------------------------------------------------------

async def open_backend_ws(ws_base: Optional[str], ext: Optional[str]):
    if not ws_base or not ext:
        return None
    url = f"{ws_base}/ws/transcript?ext={ext}"
    try:
        ws = await websockets.connect(url, ssl=_ssl_ctx(url))
        print(f"[A] backend ws connected {url}")
        return ws
    except Exception as e:
        log.warning(f"[A] backend ws connect failed: {e}")
        return None


async def close_ws_quietly(*wss):
    for ws in wss:
        try:
            if ws:
                await ws.close()
        except Exception:
            pass


# --- Main loop ---------------------------------------------------------------------

async def run(ws_base: str, ext: str, mic_name: Optional[str], loopback_name: Optional[str], lang: str):
    backend_ws = await open_backend_ws(ws_base, ext)
    tasks = []
    streams: list[sd.RawInputStream] = []

    ws_mic = None
    ws_loop = None

    try:
        if mic_name:
            q_mic, s_mic = make_reader(mic_name)
            ws_mic = await open_transcription_session("near_field", lang)
            if ws_mic:
                s_mic.start()
                streams.append(s_mic)
                tasks += [
                    asyncio.create_task(pump_audio(q_mic, ws_mic, STOP_EVT)),
                    asyncio.create_task(consume_transcripts("agent", ws_mic, backend_ws, STOP_EVT)),
                ]
                print(f'[A] mic     = "{mic_name}" rate={RATE}')

        if loopback_name:
            q_loop, s_loop = make_reader(loopback_name)
            ws_loop = await open_transcription_session("far_field", lang)
            if ws_loop:
                s_loop.start()
                streams.append(s_loop)
                tasks += [
                    asyncio.create_task(pump_audio(q_loop, ws_loop, STOP_EVT)),
                    asyncio.create_task(consume_transcripts("customer", ws_loop, backend_ws, STOP_EVT)),
                ]
                print(f'[A] loopback= "{loopback_name}" rate={RATE}')

        if not tasks:
            log.error("[A] Keine Audioquelle (--mic/--loopback).")
            return

        await STOP_EVT.wait()

    finally:
        for st in streams:
            try:
                st.stop()
            except:
                pass
            try:
                st.close()
            except:
                pass
        try:
            sd.stop()
        except:
            pass
        await close_ws_quietly(ws_mic, ws_loop, backend_ws)
        print("[A] stopped")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ws")
    p.add_argument("--ext")
    p.add_argument("--mic")
    p.add_argument("--spk")
    p.add_argument("--loopback")
    p.add_argument("--lang", default=LANG_DEFAULT)
    p.add_argument("--list-devices", action="store_true", default=False)
    args = p.parse_args()

    if args.list_devices:
        list_devices()
        return

    if not args.ws or not args.ext:
        raise SystemExit("missing --ws or --ext")
    if not OPENAI_API_KEY:
        raise SystemExit("OPENAI_API_KEY not set")

    # Signal-Handler setzen
    def handle_stop(signum, frame):
        if not STOP_EVT.is_set():
            STOP_EVT.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, handle_stop)
        except:
            pass

    try:
        asyncio.run(run(args.ws, args.ext, args.mic, args.loopback, args.lang))
    except KeyboardInterrupt:
        STOP_EVT.set()
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
