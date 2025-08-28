# app/services/paragraph_buffer.py
import asyncio
import time
from difflib import SequenceMatcher
from typing import Callable, Dict


def _sim(a, b): return SequenceMatcher(a=a.lower().strip(), b=b.lower().strip()).ratio()


class ParagraphBuffer:
    def __init__(
            self,
            target_chars: int = 200,  # Zielgröße pro Absatz
            max_sents: int = 4,  # maximal Sätze pro Absatz
            idle_flush_sec: float = 6,  # bei Stille Rest speichern
            dedup_ratio: float = 0.90,  # sehr ähnliche Absätze droppen
    ):
        self.tchars = target_chars
        self.msents = max_sents
        self.idle = idle_flush_sec
        self.dd = dedup_ratio
        self.state: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()

    async def add(self, call_id: str, sentence: str, persist: Callable[[str, str], asyncio.Future]):
        if not sentence: return
        now = time.monotonic()
        async with self._lock:
            st = self.state.setdefault(call_id, {
                "txt": "", "cnt": 0, "last": now, "task": None, "last_saved": ""
            })
            # anfügen
            st["txt"] = (st["txt"] + " " + sentence).strip() if st["txt"] else sentence.strip()
            st["cnt"] += 1
            st["last"] = now

            # Bedingungen zum Speichern?
            ready = (len(st["txt"]) >= self.tchars) or (st["cnt"] >= self.msents)
            if ready:
                para = st["txt"].strip()
                # Dedup vs. letzter Absatz
                if not st["last_saved"] or _sim(para, st["last_saved"]) < self.dd:
                    await persist(call_id, para)
                    st["last_saved"] = para
                st["txt"] = "";
                st["cnt"] = 0

            # Idle-Task
            if st["task"] is None:
                st["task"] = asyncio.create_task(self._idle_watch(call_id, persist))

    async def force_flush(self, call_id: str, persist: Callable[[str, str], asyncio.Future]):
        async with self._lock:
            st = self.state.get(call_id)
            if not st or not st["txt"]: return
            para = st["txt"].strip()
            st["txt"] = "";
            st["cnt"] = 0
        await persist(call_id, para)

    async def clear(self, call_id: str):
        async with self._lock:
            st = self.state.pop(call_id, None)
            if st and st.get("task"):
                try:
                    st["task"].cancel()
                except:
                    pass

    async def _idle_watch(self, call_id: str, persist):
        try:
            while True:
                await asyncio.sleep(self.idle)
                async with self._lock:
                    st = self.state.get(call_id)
                    if not st: return
                    if (time.monotonic() - st["last"]) >= self.idle and st["txt"]:
                        para = st["txt"].strip()
                        st["txt"] = "";
                        st["cnt"] = 0
                    else:
                        para = ""
                if para:
                    await persist(call_id, para)
        except asyncio.CancelledError:
            return
        finally:
            async with self._lock:
                st = self.state.get(call_id)
                if st: st["task"] = None
