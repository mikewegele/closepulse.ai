import argparse
import asyncio
import base64
import json
import os
import queue

import sounddevice as sd
import websockets

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
RT_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-mini-transcribe"
HDR = {"Authorization": f"Bearer {OPENAI_API_KEY}", "OpenAI-Beta": "realtime=v1"}
RATE = 16000
CHUNK = int(RATE * 0.02)


def list_devices():
    devs = sd.query_devices()
    ins = [d["name"] for d in devs if d.get("max_input_channels", 0) > 0]
    outs = [d["name"] for d in devs if d.get("max_output_channels", 0) > 0]
    print(json.dumps({"inputs": ins, "outputs": outs}, ensure_ascii=False))


class InReader:
    def __init__(self, name=None):
        self.q = queue.Queue()
        self.stream = sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK, device=name,
                                        callback=self.cb)

    def cb(self, indata, frames, t, status):
        self.q.put(bytes(indata))

    def start(self):
        self.stream.start()

    def stop(self):
        try:
            self.stream.stop(); self.stream.close()
        except:
            pass

    def read(self):
        return self.q.get()


async def open_session(noise, lang):
    ws = await websockets.connect(RT_URL, extra_headers=HDR, ping_interval=20, max_size=10_000_000)
    cfg = {
        "type": "session.update",
        "session": {
            "object": "realtime.transcription_session",
            "input_audio_format": "pcm16",
            "input_audio_transcription": [{"model": "gpt-4o-mini-transcribe", "prompt": "", "language": lang}],
            "turn_detection": {"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300,
                               "silence_duration_ms": 500},
            "input_audio_noise_reduction": {"type": noise},
            "include": []
        }
    }
    await ws.send(json.dumps(cfg))
    return ws


async def pump(reader, ws):
    loop = asyncio.get_event_loop()
    while True:
        buf = await loop.run_in_executor(None, reader.read)
        await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": base64.b64encode(buf).decode("ascii")}))


async def consume(role, ws, tx_ws):
    partial = {}
    async for msg in ws:
        evt = json.loads(msg)
        t = evt.get("type")
        if t == "conversation.item.input_audio_transcription.delta":
            iid = evt["item_id"];
            partial[iid] = partial.get(iid, "") + evt.get("delta", "")
        elif t == "conversation.item.input_audio_transcription.completed":
            iid = evt["item_id"]
            transcript = evt.get("transcript") or partial.get(iid, "")
            partial.pop(iid, None)
            if role == "customer" and transcript.strip():
                await tx_ws.send(json.dumps({"role": "customer", "text": transcript.strip()}))


async def run(ws_base, ext, mic_name, loop_name):
    tx = await websockets.connect(f"{ws_base}/ws/transcript?ext={ext}")
    ws_a = await open_session("near_field", "de")
    ws_c = await open_session("far_field", "de")
    mic = InReader(mic_name)
    loop = InReader(loop_name)
    mic.start();
    loop.start()
    await asyncio.gather(
        pump(mic, ws_a),
        pump(loop, ws_c),
        consume("agent", ws_a, tx),
        consume("customer", ws_c, tx)
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ws")
    p.add_argument("--ext")
    p.add_argument("--mic")
    p.add_argument("--spk")
    p.add_argument("--loopback")
    p.add_argument("--list-devices", action="store_true")
    args = p.parse_args()
    if args.list_devices:
        list_devices()
        return
    asyncio.run(run(args.ws, args.ext, args.mic, args.loopback))


if __name__ == "__main__":
    main()
