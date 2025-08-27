import logging
import time

from ..agents import runner, database_agent
from ..db import SessionLocal
from ..utils import get_or_create_conversation, add_message

log = logging.getLogger("app")


async def anonymize_and_store(text: str, mime: str, name: str, x_conversation_id: str | None):
    t0 = time.perf_counter()
    anonym_text = ""
    try:
        da_out = await runner.run(database_agent, [{"role": "user", "content": text}])
        anonym_text = (getattr(da_out, "final_output", "") or "").strip()
    except Exception as e:
        log.warning("anonymize failed: %s", e)

    if not anonym_text:
        log.info("anonymize_and_store: empty anonym_text -> skip persist")
        return

    try:
        async with SessionLocal() as db:
            conv_id = await get_or_create_conversation(db, x_conversation_id)
            await add_message(
                db, conv_id, role="user", content=anonym_text, source="transcribe",
                meta={"mime": mime, "filename": name},
            )
        log.info("anonymize_and_store done in %.3fs", time.perf_counter() - t0)
    except Exception as e:
        log.exception("persist failed: %s", e)
