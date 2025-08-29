# app/services/snapshot.py
from ..logging import setup_logging
from ..services.anonymize import anonymize_and_store
from ..state.live_store import live_store

log = setup_logging()


async def save_snapshot(call_id: str, reason: str = "button") -> int:
    """
    Speichert genau EINEN großen Textblock:
    - Beim ersten Klick: alles seit Callbeginn
    - Danach: nur Delta seit dem letzten Snapshot
    - Gibt Anzahl gespeicherter Zeichen zurück.
    """
    delta, start, end = live_store.delta_since_saved(call_id)
    text = (delta or "").strip()
    if not text:
        log.info("📝 snapshot(%s): nichts zu speichern (delta=0)", reason)
        return 0

    # EIN Speichervorgang
    await anonymize_and_store(text, "text/plain", f"snapshot_{reason}_{end}.txt", call_id)
    live_store.mark_saved(call_id, end)
    log.info("📝 snapshot(%s): saved %d chars (offset %d→%d)", reason, len(text), start, end)
    return len(text)
