# app/state/live_store.py
import asyncio
import json
import os
import tempfile
import time
from typing import Dict, Optional, Tuple

from ..config import settings

# Eine Zeile pro Call persistieren
_PERSIST = str(getattr(settings, "PERSIST_LIVE_ONE_ROW", "1")).lower() in ("1", "true", "yes", "on")
_LIVE_DIR = getattr(settings, "LIVE_DIR", "./live_store")


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _safe_path(call_id: str) -> str:
    return os.path.join(_LIVE_DIR, f"{call_id}.json")


def _atomic_write_json(path: str, data: dict):
    dirn = os.path.dirname(path)
    _ensure_dir(dirn)
    with tempfile.NamedTemporaryFile("w", dir=dirn, delete=False, encoding="utf-8") as tmp:
        # exakt EINE Zeile JSON (überschreibt die Datei anschließend atomar)
        json.dump(data, tmp, ensure_ascii=False, separators=(",", ":"))
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = tmp.name
    os.replace(tmp_path, path)


def _read_json(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


class _LiveStore:
    """
    - In-Memory Buffer hält den aktuellen Transkript-String pro Call.
    - Auf jede Änderung wird die JSON-Datei <call_id>.json EINZEILIG überschrieben.
    - saved_offset wird mitgeführt, damit Snapshots Deltas speichern können.
    """

    def __init__(self):
        self._buf: Dict[str, str] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._ext: Dict[str, str] = {}
        self._saved_offset: Dict[str, int] = {}
        if _PERSIST:
            _ensure_dir(_LIVE_DIR)

    def _lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _get_saved_offset(self, call_id: str) -> int:
        # Wenn im Speicher nichts ist, versuche aus Datei zu lesen
        if call_id in self._saved_offset:
            return int(self._saved_offset[call_id])
        if _PERSIST:
            row = _read_json(_safe_path(call_id)) or {}
            off = int(row.get("saved_offset") or 0)
            self._saved_offset[call_id] = off
            return off
        return 0

    async def _write_one_row(
            self,
            call_id: str,
            ext_id: Optional[str],
            *,
            inc_segment: int = 0,
            overwrite_text: Optional[str] = None,
            touch_only: bool = False,
    ):
        """
        Schreibt genau EINE JSON-Zeile für den Call:
        - transcript = Buffer (oder overwrite_text)
        - segments wird um inc_segment erhöht (oder unverändert bei touch_only)
        - created_at bleibt stabil, updated_at wird aktualisiert
        - saved_offset bleibt erhalten
        """
        if not _PERSIST:
            return
        path = _safe_path(call_id)
        now = time.time()

        async with self._lock(call_id):
            row = _read_json(path) or {}

            # Stabil lassen:
            created_at = float(row.get("created_at") or now)

            # Aktueller Text
            text = (overwrite_text if overwrite_text is not None else self._buf.get(call_id, "")) or ""
            old_segments = int(row.get("segments") or 0)
            segments = old_segments if touch_only else (old_segments + int(inc_segment))

            # saved_offset aus Speicher oder Row übernehmen
            saved_offset = int(row.get("saved_offset") or self._get_saved_offset(call_id) or 0)

            data = {
                "call_id": call_id,
                "ext_id": (ext_id if ext_id is not None else row.get("ext_id")),
                "transcript": text.strip(),
                "segments": segments,
                "created_at": created_at,
                "updated_at": now,
                "saved_offset": saved_offset,
            }
            _atomic_write_json(path, data)

    # -------- Public API --------

    async def set_ext_id(self, call_id: str, ext_id: str):
        self._ext[call_id] = ext_id
        # initiale Zeile (ohne Segment-Erhöhung)
        await self._write_one_row(call_id, ext_id, inc_segment=0)

    def add_text(self, call_id: str, text: str):
        """Append in Memory, dann EINZEILIG überschreiben (segments +1)."""
        if not text:
            return
        buf = self._buf.get(call_id, "")
        self._buf[call_id] = (buf + (" " if buf else "") + text).strip()
        asyncio.create_task(self._write_one_row(call_id, self._ext.get(call_id), inc_segment=1))

    def full_text(self, call_id: str) -> str:
        return self._buf.get(call_id, "")

    async def replace_text(self, call_id: str, new_text: str):
        """Hard-Set Text und überschreiben (segments nicht erhöhen)."""
        self._buf[call_id] = (new_text or "").strip()
        await self._write_one_row(call_id, self._ext.get(call_id), inc_segment=0, overwrite_text=self._buf[call_id])

    def delta_since_saved(self, call_id: str) -> Tuple[str, int, int]:
        """Gibt (delta_text, start_offset, end_offset) zurück basierend auf saved_offset."""
        full = self._buf.get(call_id, "") or ""
        start = self._get_saved_offset(call_id)
        if start < 0 or start > len(full):
            start = 0
        end = len(full)
        delta = full[start:end]
        return delta, start, end

    def mark_saved(self, call_id: str, new_offset: int):
        """Setzt saved_offset in Memory und Datei (ohne segments zu erhöhen)."""
        self._saved_offset[call_id] = int(new_offset)
        if _PERSIST:
            path = _safe_path(call_id)
            now = time.time()

            # Datei updaten, aber transcript unverändert lassen
            async def _persist():
                async with self._lock(call_id):
                    row = _read_json(path) or {}
                    row["saved_offset"] = int(new_offset)
                    row["updated_at"] = now
                    # Safety: falls Datei noch nicht existierte
                    row.setdefault("call_id", call_id)
                    row.setdefault("ext_id", self._ext.get(call_id))
                    row.setdefault("transcript", self._buf.get(call_id, ""))
                    row.setdefault("segments", 0)
                    row.setdefault("created_at", now)
                    _atomic_write_json(path, row)

            asyncio.create_task(_persist())

    def clear(self, call_id: str):
        self._buf.pop(call_id, None)
        self._ext.pop(call_id, None)
        self._saved_offset.pop(call_id, None)

    async def mark_ended(self, call_id: str):
        """Nur updated_at anfassen und EINZEILIG schreiben (touch)."""
        await self._write_one_row(call_id, self._ext.get(call_id), touch_only=True)


live_store = _LiveStore()
