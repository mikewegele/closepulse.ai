# app/vad.py
import collections
import time

import numpy as np


class SilenceDetector:
    """
    Einfache, schnelle Silence-Detection per RMS (Energie).
    - Erwartet 20-ms PCM16@16 kHz Mono Frames (passt zu deinem Stream).
    - silent, wenn RMS unter threshold.
    - Löst aus, wenn 'silence_sec' am Stück still war.
    """

    def __init__(self, silence_sec: float = 1.0, frame_ms: int = 20, sample_rate: int = 16000,
                 threshold: float = 0.01, min_gap: float = 1.0):
        self.frames_needed = int(silence_sec * 1000 / frame_ms)
        self.recent = collections.deque(maxlen=self.frames_needed)
        self.last_trigger = 0.0
        self.min_gap = float(min_gap)
        self.sr = int(sample_rate)
        self.threshold = float(threshold)

    @staticmethod
    def _rms_pcm16(frame: bytes) -> float:
        # PCM16 little-endian → float32 [-1, 1]
        if not frame:
            return 0.0
        x = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
        if x.size == 0:
            return 0.0
        x /= 32768.0
        # RMS
        return float(np.sqrt(np.mean(x * x)))

    def update(self, pcm_frame: bytes) -> bool:
        rms = self._rms_pcm16(pcm_frame)
        silent = rms < self.threshold
        self.recent.append(silent)
        # Vollständiges Silence-Fenster + Entprellung (min_gap)
        if len(self.recent) == self.frames_needed and all(self.recent):
            now = time.time()
            if (now - self.last_trigger) >= self.min_gap:
                self.last_trigger = now
                return True
        return False
