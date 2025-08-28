# app/services/sentence_buffer.py
import asyncio
import re
import time
from difflib import SequenceMatcher
from typing import Callable, Dict

ABBR = {
    "z.b.", "z. b.", "u.a.", "usw.", "bzw.", "ca.", "dr.", "prof.", "etc.",
    "sr.", "jr.", "nr.", "std.", "min.", "sek."
}

SENT_END_RE = re.compile(r'(?s)^(.+?[.!?…]["»”\')\]]*)(?:\s+|$)')


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(a=a.lower().strip(), b=b.lower().strip()).ratio()


class SentenceBuffer:
    def __init__(
            self,
            idle_flush_sec: float = 2.0,  # nach Stille X s Rest flushen
            min_sentence_len: int = 5,  # zu kurze Fetzen ignorieren
            min_flush_chars: int = 28,  # wenn <28 Zeichen → erst sammeln
            min_flush_words: int = 4,  # oder <4 Wörter → sammeln
            short_join_max_wait: float = 4.0,  # spätes Flushen eines Short-Carries
            dedup_ratio: float = 0.92,  # ~gleich → drop
            max_buffer_chars: int = 4000,  # Schutz
    ):
        self.idle = idle_flush_sec
        self.minlen = min_sentence_len
        self.minchars = min_flush_chars
        self.minwords = min_flush_words
        self.short_wait = short_join_max_wait
        self.dedup_ratio = dedup_ratio
        self.maxbuf = max_buffer_chars

        # call_id → state
        self.state: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()

    async def add(self, call_id: str, text: str, on_flush: Callable[[str, str], asyncio.Future]):
        if not text:
            return
        now = time.monotonic()
        async with self._lock:
            st = self.state.setdefault(call_id, {
                "buf": "",  # noch unvollständiger Text
                "carry": "",  # kurzer abgeschl. Satz, wartet auf Join
                "last": now,  # letzte Aktivität
                "last_saved": "",  # zuletzt persistierter Satz (für Dedup)
                "carry_since": None,  # Startzeit des current carry
                "task": None,  # idle task
            })
            st["buf"] = (st["buf"] + " " + text).strip() if st["buf"] else text.strip()
            st["last"] = now

            if len(st["buf"]) > self.maxbuf:
                st["buf"] = st["buf"][-self.maxbuf:]  # tail keep

            # vollständige Sätze vom Kopf abziehen
            sentences, remainder = self._split_complete(st["buf"])
            st["buf"] = remainder

            for s in sentences:
                s = s.strip()
                if len(s) < self.minlen:
                    continue

                # Dedup gegen zuletzt gespeicherten Satz
                if st["last_saved"] and _similar(s, st["last_saved"]) >= self.dedup_ratio:
                    continue

                # Short-Join Logik
                if self._is_short(s):
                    # an den Carry anhängen
                    st["carry"] = (st["carry"] + " " + s).strip() if st["carry"] else s
                    st["carry_since"] = st["carry_since"] or now
                    continue
                else:
                    # „richtiger“ Satz: ggf. Carry voranstellen
                    if st["carry"]:
                        s = (st["carry"] + " " + s).strip()
                        st["carry"] = ""
                        st["carry_since"] = None

                    await on_flush(call_id, s)
                    st["last_saved"] = s

            # Idle-Watcher starten
            if st["task"] is None:
                st["task"] = asyncio.create_task(self._idle_watch(call_id, on_flush))

    async def force_flush(self, call_id: str, on_flush: Callable[[str, str], asyncio.Future]):
        """Alles flushen (z. B. bei Hangup)."""
        async with self._lock:
            st = self.state.get(call_id)
            if not st:
                return
            parts = []
            if st.get("carry"):
                parts.append(st["carry"].strip())
                st["carry"] = ""
                st["carry_since"] = None
            if st.get("buf"):
                parts.append(st["buf"].strip())
                st["buf"] = ""
        if parts:
            text = " ".join(p for p in parts if p)
            await on_flush(call_id, text)

    async def clear(self, call_id: str):
        async with self._lock:
            st = self.state.pop(call_id, None)
            if st and st.get("task"):
                try:
                    st["task"].cancel()
                except Exception:
                    pass

    async def _idle_watch(self, call_id: str, on_flush):
        try:
            while True:
                await asyncio.sleep(self.idle)
                async with self._lock:
                    st = self.state.get(call_id)
                    if not st:
                        return
                    now = time.monotonic()
                    remainder = ""
                    # 1) länger still → Rest flushen
                    if (now - st["last"]) >= self.idle and st["buf"]:
                        remainder = st["buf"].strip()
                        st["buf"] = ""

                    # 2) Carry zu lange offen → flush erzwingen
                    if st["carry"] and st["carry_since"] and (now - st["carry_since"]) >= self.short_wait:
                        remainder = ((st["carry"] + " " + remainder).strip() if remainder else st["carry"].strip())
                        st["carry"] = ""
                        st["carry_since"] = None

                if remainder:
                    await on_flush(call_id, remainder)
                    # last_saved setzen für dedup
                    async with self._lock:
                        st = self.state.get(call_id)
                        if st:
                            st["last_saved"] = remainder
        except asyncio.CancelledError:
            return
        finally:
            async with self._lock:
                st = self.state.get(call_id)
                if st:
                    st["task"] = None

    def _split_complete(self, buf: str):
        out = []
        txt = buf.strip()
        while txt:
            m = SENT_END_RE.match(txt)
            if not m:
                break
            cand = m.group(1).strip()
            tail = cand[-6:].lower()
            if any(tail.endswith(a) for a in ABBR):
                break
            out.append(cand)
            txt = txt[len(m.group(0)):].lstrip()
        return out, txt

    def _is_short(self, s: str) -> bool:
        # kurze Fetzen sammeln
        words = s.split()
        return (len(s) < self.minchars) or (len(words) < self.minwords)
