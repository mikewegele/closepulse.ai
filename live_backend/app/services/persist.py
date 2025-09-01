import logging
import time

from ..db import SessionLocal
from ..utils import add_message

log = logging.getLogger("app")


async def anonymize_and_store(text: str, mime: str, name: str, x_conversation_id: str | None):
    t0 = time.perf_counter()
    anonym_text = text
    if not anonym_text:
        return
    try:
        async with SessionLocal() as db:
            await add_message(
                db, x_conversation_id, role="user", content=anonym_text, source="transcribe",
                meta={"mime": mime, "filename": name},
            )
        log.info("persisted in %.3fs", time.perf_counter() - t0)
    except Exception as e:
        log.exception("persist failed: %s", e)
