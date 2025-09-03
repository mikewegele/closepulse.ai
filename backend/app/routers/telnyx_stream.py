# app/routes/telnyx_stream.py
from __future__ import annotations

import base64
import json
import os
import time

import audioop
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from models import LiveCall  # dein ORM-Modell
from sqlalchemy import select

from backend.config import settings
from ..db import SessionLocal
from ..logging import setup_logging
from ..services.audio_sink import audio_sinks
from ..state.live_store import live_store

log = setup_logging()
router = APIRouter()


def mulaw_to_lin16(mu: bytes) -> bytes:
    """Telnyx µ-law @8k → PCM16 (mono, 8 kHz)."""
    if not mu:
        return b""
    return audioop.ulaw2lin(mu, 2)


def _get_audio_b64(evt: dict) -> str | None:
    pl = evt.get("payload") or evt.get("media") or {}
    return pl.get("payload") or pl.get("data")


def _wav_path_for_call(call_id: str) -> str:
    base = getattr(settings, "AUDIO_DIR", "./audio")
    return os.path.join(base, f"{call_id}.wav")


@router.websocket("/telnyx/stream")
async def telnyx_stream(ws: WebSocket):
    await ws.accept()

    call_id = ws.query_params.get("call_id") or "unknown"
    ext_id = ws.query_params.get("ext_id") or settings.EXTERNAL_CALL_ID

    # File-Sink öffnen (schreibt schnell & hält Filehandle offen)
    sink = audio_sinks.open(call_id, getattr(settings, "AUDIO_DIR", "./audio"), ext_id)
    await live_store.set_ext_id(call_id, ext_id)

    # Metriken / Qualität
    packet_count = 0
    bytes_total = 0
    start_t = time.monotonic()
    first_pkt_t = None
    last_pkt_t = None
    prev_pkt_t = None
    max_gap = 0.0
    min_bytes = 10 ** 9
    max_bytes = 0

    log.info("telnyx_stream: START call=%s ext=%s sink=%s", call_id, ext_id, _wav_path_for_call(call_id))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                evt = json.loads(raw)
            except Exception:
                continue

            et = (evt.get("event") or evt.get("type") or "").lower()

            if et == "media":
                b64 = _get_audio_b64(evt)
                if not b64:
                    continue

                try:
                    mu = base64.b64decode(b64)
                except Exception:
                    continue

                pcm8k = mulaw_to_lin16(mu)
                # Sicherheit: nur gerade Bytezahl (16-bit)
                if not pcm8k or (len(pcm8k) & 1):
                    continue

                # Metriken
                now = time.monotonic()
                if first_pkt_t is None:
                    first_pkt_t = now
                if prev_pkt_t is not None:
                    gap = now - prev_pkt_t
                    if gap > max_gap:
                        max_gap = gap
                prev_pkt_t = now

                packet_count += 1
                b = len(pcm8k)
                bytes_total += b
                if b < min_bytes:
                    min_bytes = b
                if b > max_bytes:
                    max_bytes = b
                last_pkt_t = now

                # *** Hot-Loop: nur schnelles File-Append, KEINE DB-Transaktion! ***
                try:
                    sink.append_pcm8k_lin16(pcm8k)
                except Exception as e:
                    log.warning("telnyx_stream: sink append failed call=%s err=%s", call_id, e)

                # Alle 50 Pakete mal loggen
                if (packet_count % 50) == 0:
                    expected_sec = packet_count * 0.02  # 20ms Frames
                    elapsed = now - start_t
                    log.info(
                        "telnyx_stream: call=%s pkts=%d exp=%.2fs elapsed=%.2fs bytes8k=%d minB=%d maxB=%d maxGap=%.3fs",
                        call_id, packet_count, expected_sec, elapsed, bytes_total, min_bytes, max_bytes, max_gap
                    )

                continue

            if et == "stop":
                # Telnyx schickt 'stop' am Ende der Medien
                break

            # Andere Events ignorieren
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.exception("telnyx_stream: error call=%s err=%s", call_id, e)
    finally:
        try:
            await ws.close()
        except Exception:
            pass

        # File sink sauber schließen (Header finalisieren)
        try:
            audio_sinks.close(call_id)
        except Exception:
            pass

        media_window = (last_pkt_t - first_pkt_t) if first_pkt_t and last_pkt_t else 0.0
        expected_sec = packet_count * 0.02
        wav_path = _wav_path_for_call(call_id)
        file_size = os.path.getsize(wav_path) if os.path.exists(wav_path) else 0
        # Datenbereich (grob) ohne Header (~44B)
        data_bytes_on_disk = max(0, file_size - 44)

        log.info(
            "telnyx_stream: END call=%s pkts=%d media_window=%.2fs expected=%.2fs bytes8k=%d on_disk=%d minB=%d maxB=%d maxGap=%.3fs",
            call_id, packet_count, media_window, expected_sec, bytes_total, data_bytes_on_disk,
            min_bytes if min_bytes != 10 ** 9 else 0, max_bytes, max_gap
        )

        # *** DB-Finalisierung EINMAL am Ende ***
        try:
            async with SessionLocal() as db:
                # gibt es bereits eine Row?
                res = await db.execute(select(LiveCall).where(LiveCall.conversation_id == call_id))
                row = res.scalars().first()
                now_utc = time.time()

                if row:
                    row.chunk_count = packet_count
                    row.audio_bytes_total = data_bytes_on_disk
                    row.audio_path = wav_path
                    row.updated_at = row.updated_at  # ORM hält Zeit; ggf. DB default nutzen
                    meta = dict(row.meta or {})
                    meta.update({
                        "source": "telnyx",
                        "min_bytes": min_bytes if min_bytes != 10 ** 9 else 0,
                        "max_bytes": max_bytes,
                        "max_gap_sec": round(max_gap, 3),
                        "media_window_sec": round(media_window, 3),
                        "expected_sec": round(expected_sec, 3),
                    })
                    row.meta = meta
                    await db.commit()
                else:
                    # neu anlegen
                    new_row = LiveCall(
                        conversation_id=call_id,
                        external_id=ext_id,
                        audio_path=wav_path,
                        chunk_count=packet_count,
                        audio_bytes_total=data_bytes_on_disk,
                        meta={
                            "source": "telnyx",
                            "min_bytes": min_bytes if min_bytes != 10 ** 9 else 0,
                            "max_bytes": max_bytes,
                            "max_gap_sec": round(max_gap, 3),
                            "media_window_sec": round(media_window, 3),
                            "expected_sec": round(expected_sec, 3),
                        },
                    )
                    db.add(new_row)
                    await db.commit()
        except Exception as e:
            log.warning("telnyx_stream: finalize metrics failed call=%s err=%s", call_id, e)
