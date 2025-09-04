#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
closepulse_agent.py — STT-Only Agent (Mac mic -> OpenAI Realtime Transcription -> Backend WS)

Features
- Liest Mac-Mikro (oder beliebiges Input-Device via Substring)
- Streamt PCM16 an Realtime WS (intent=transcription) mit serverseitigem VAD
- Empfangt Transkript-Events (delta/completed) und sendet fertige Texte ans Backend
- Sauberer Shutdown (Mic bleibt nicht offen)
- Optional: Loopback-Zuspielung (z.B. "BlackHole 2ch") als "customer"-Spur

Usage (Beispiel)
  python closepulse_agent.py \
    --ws ws://127.0.0.1:8000 \
    --ext EXT_FIXED_ID \
    --mic "MacBook Pro-Mikrofon" \
    --lang de

Env (.env)
  OPENAI_API_KEY=sk-...
  REALTIME_MODEL=gpt-realtime              # ignoriert (nur für future use)
  TRANSCRIBE_MODEL=gpt-4o-mini-transcribe  # <- wichtig
  CP_LANG=de
  CP_RATE_IN=16000
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import signal
import ssl
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
        # indata: bytes-like (int16) wegen RawInputStream + dtype='int16'
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
    """
    Baut eine Realtime-WS-Verbindung auf und konfiguriert eine Transkriptions-Session
    mit serverseitigem VAD. Wichtig: input_audio_format ist ein STRING.
    """
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
        # Erste Server-Nachricht (session.created) ggf. lesen, aber nicht erzwingen
        try:
            raw0 = await asyncio.wait_for(ws.recv(), timeout=5)
            _evt0 = json.loads(raw0)
            log.debug(f"[A] first evt: {_evt0.get('type')}")
        except Exception:
            pass

        # Achtung: input_audio_format ist STRING; include kann leer bleiben.
        await ws.send(json.dumps({
            "type": "transcription_session.update",
            "session": {
                "input_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": TRANSCRIBE_MODEL,
                    "language": lang,
                    "prompt": ""
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 700
                },
                "input_audio_noise_reduction": {"type": noise_type},
                # "include": []   # optional; leer lassen ist auch ok
            }
        }))

        # Auf session.updated warten
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            evt = json.loads(raw)
            if evt.get("type") == "transcription_session.updated":
                log.debug("[A] transcription_session.updated")
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


async def pump_audio(q: asyncio.Queue, ws, stop_evt: asyncio.Event, vad_enabled: bool = True):
    """
    Pumpt Audio-Chunks (base64 PCM16) zum Realtime-WS.
    WICHTIG: Bei aktivem VAD KEINE Commits senden. Server commitet selbst.
    """
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
            # Kein commit bei VAD!
        except Exception as e:
            log.debug(f"[A] pump send fail: {e}")
            await asyncio.sleep(0.05)


async def consume_transcripts(role: str, ws, backend_ws, stop_evt: asyncio.Event):
    """
    Liest alle Events vom Realtime-WS, sammelt deltas und sendet bei 'completed'
    das fertige Transkript ans Backend (role: 'agent' oder 'customer').
    """

    partial = {}
    if ws is None:
        return

    try:
        async for raw in ws:
            if stop_evt.is_set():
                break

            try:
                evt = json.loads(raw)
            except Exception:
                continue

            t = evt.get("type")
            # Debug: alles loggen, außer die recht spammy delta-Events
            if t not in (
                    "conversation.item.input_audio_transcription.delta",
                    "conversation.item.input_audio_transcription.completed",
                    "rate_limits.updated",
                    "input_audio_buffer.speech_started",
                    "input_audio_buffer.speech_stopped",
                    "input_audio_buffer.committed",
            ):
                log.debug(f"[A] evt {t}")

            if t == "input_audio_buffer.speech_started":
                log.debug("[A] VAD: speech_started")
            elif t == "input_audio_buffer.speech_stopped":
                log.debug("[A] VAD: speech_stopped")
            elif t == "conversation.item.input_audio_transcription.delta":
                iid = evt.get("item_id")
                if iid:
                    partial[iid] = partial.get(iid, "") + (evt.get("delta") or "")
            elif t == "conversation.item.input_audio_transcription.completed":
                iid = evt.get("item_id")
                transcript = (evt.get("transcript") or partial.get(iid, "") or "").strip()
                partial.pop(iid, None)
                if not transcript:
                    continue
                snip = (transcript[:100] + ("…" if len(transcript) > 100 else "")).replace("\n", " ")
                print(f'[A] {role}: "{snip}"')
                if role in ("customer", "agent") and backend_ws:
                    try:
                        await backend_ws.send(json.dumps({"role": role, "text": transcript}))
                    except Exception as e:
                        log.warning(f"[A] backend send fail: {e}")
            elif t == "error":
                log.warning(f"[A] realtime error: {evt}")
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
    stop_evt = asyncio.Event()

    def stop_all(*_):
        if not stop_evt.is_set():
            stop_evt.set()

    # Signals fangen (Ctrl+C, Quit)
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, stop_all)
        except Exception:
            pass

    ws_mic = None
    ws_loop = None

    try:
        if mic_name:
            q_mic, s_mic = make_reader(mic_name)
            ws_mic = await open_transcription_session("near_field", lang)
            if ws_mic is None:
                raise RuntimeError("Realtime (mic) session failed")

            s_mic.start()
            streams.append(s_mic)
            tasks += [
                asyncio.create_task(pump_audio(q_mic, ws_mic, stop_evt, vad_enabled=True)),
                asyncio.create_task(consume_transcripts("agent", ws_mic, backend_ws, stop_evt)),
            ]
            print(f'[A] mic     = "{mic_name}" rate={RATE}')

        if loopback_name:
            q_loop, s_loop = make_reader(loopback_name)
            ws_loop = await open_transcription_session("far_field", lang)
            if ws_loop is None:
                raise RuntimeError("Realtime (loopback) session failed")

            s_loop.start()
            streams.append(s_loop)
            tasks += [
                asyncio.create_task(pump_audio(q_loop, ws_loop, stop_evt, vad_enabled=True)),
                asyncio.create_task(consume_transcripts("customer", ws_loop, backend_ws, stop_evt)),
            ]
            print(f'[A] loopback= "{loopback_name}" rate={RATE}')

        if not tasks:
            log.error("[A] Keine Audioquelle übergeben (--mic/--loopback).")
            return

        # Warten bis Stop
        stop_fut = asyncio.get_event_loop().create_future()

        async def wait_stop():
            await stop_evt.wait()
            if not stop_fut.done():
                stop_fut.set_result(True)

        waiter = asyncio.create_task(wait_stop())
        await asyncio.gather(*tasks, stop_fut)
        waiter.cancel()

    finally:
        # Streams beenden (Mic AUS)
        for st in streams:
            try:
                st.stop()
            except Exception:
                pass
            try:
                st.close()
            except Exception:
                pass
        try:
            sd.stop()
        except Exception:
            pass

        # Sockets schließen
        await close_ws_quietly(ws_mic, ws_loop, backend_ws)
        print("[A] stopped")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ws", help="Backend WS Base (z.B. ws://127.0.0.1:8000)")
    p.add_argument("--ext", help="External Call ID")
    p.add_argument("--mic", help="Mic Device Name (Substring)")
    p.add_argument("--spk", help="(ignoriert in STT-only)")
    p.add_argument("--loopback", help="Loopback Device Name (z.B. BlackHole 2ch)")
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

    asyncio.run(run(args.ws, args.ext, args.mic, args.loopback, args.lang))


if __name__ == "__main__":
    main()
