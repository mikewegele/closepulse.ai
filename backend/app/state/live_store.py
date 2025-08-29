# app/state/live_store.py
import time
from collections import defaultdict
from typing import Tuple


class LiveStore:
    def __init__(self):
        self._chunks = defaultdict(list)  # call_id -> [str, ...]
        self._saved_offset = {}  # call_id -> int (Zeichen-Offset zuletzt gespeichert)
        self._ts = {}  # call_id -> float (last update)

    def add_text(self, call_id: str, text: str):
        if not call_id or not text:
            return
        self._chunks[call_id].append(text)
        self._ts[call_id] = time.time()

    def full_text(self, call_id: str) -> str:
        return " ".join(self._chunks.get(call_id, []))

    def delta_since_saved(self, call_id: str) -> Tuple[str, int, int]:
        """
        returns (delta_text, start_offset, end_offset)
        - start_offset = letzter gespeicherter Offset (0 wenn nie)
        - end_offset   = aktuelle Gesamtlänge
        - delta_text   = full_text[start_offset:end_offset]
        """
        full = self.full_text(call_id)
        start = int(self._saved_offset.get(call_id, 0))
        if start < 0 or start > len(full):
            start = 0
        end = len(full)
        return full[start:end], start, end

    def mark_saved(self, call_id: str, upto_len: int):
        self._saved_offset[call_id] = int(upto_len)

    def clear(self, call_id: str):
        self._chunks.pop(call_id, None)
        self._saved_offset.pop(call_id, None)
        self._ts.pop(call_id, None)


live_store = LiveStore()
