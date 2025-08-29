# app/services/audio_sink.py
import audioop
import os
import time
import wave


class AudioSink:
    def __init__(self, base_dir: str, file_id: str):
        os.makedirs(base_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        self.path = os.path.join(base_dir, f"{file_id}-{ts}.wav")
        self.w = wave.open(self.path, "wb")
        self.w.setnchannels(1)
        self.w.setsampwidth(2)
        self.w.setframerate(16000)

    def append_pcm8k_lin16(self, pcm8k: bytes):
        if not pcm8k:
            return
        out, _ = audioop.ratecv(pcm8k, 2, 1, 8000, 16000, None)
        self.w.writeframes(out)

    def close(self):
        try:
            self.w.close()
        except Exception:
            pass


class AudioSinkStore:
    def __init__(self):
        self._sinks = {}

    def open(self, key: str, base_dir: str, file_id: str):
        if key in self._sinks:
            return self._sinks[key]
        sink = AudioSink(base_dir, file_id)
        self._sinks[key] = sink
        return sink

    def get(self, key: str):
        return self._sinks.get(key)

    def close(self, key: str):
        sink = self._sinks.pop(key, None)
        if sink:
            sink.close()


audio_sinks = AudioSinkStore()
