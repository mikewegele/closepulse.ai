import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, Any

import openai
from agents import Runner
from fastapi import HTTPException

from backend.closepulse_agents import combo_agent

logging.basicConfig(level=os.environ.get("BACKEND_LOG_LEVEL", "INFO"))
log = logging.getLogger("cp.backend")

openai.api_key = os.environ.get("OPENAI_API_KEY", "")
runner = Runner()


def now_berlin() -> datetime:
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("Europe/Berlin")
        return datetime.now(tz=tz)
    except Exception:
        return datetime.utcnow()


def now_berlin_iso_date() -> str:
    return now_berlin().date().isoformat()


def system_date_message() -> Dict[str, str]:
    return {"role": "system", "content": f"Heute ist der {now_berlin_iso_date()}"}


async def with_timeout(coro, timeout: float, label: str):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"{label} timed out after {timeout}s")


async def make_suggestions(user_text: str) -> Dict[str, Any]:
    t0 = time.perf_counter()

    payload = [
        {"role": "user", "content": user_text},
        system_date_message(),
    ]

    res = await with_timeout(
        runner.run(combo_agent, payload),
        timeout=12,
        label="make_suggestions",
    )

    raw = getattr(res, "final_output", "") or "{}"
    try:
        data = json.loads(raw)
    except Exception:
        log.exception("Failed to parse agent output as JSON")
        data = {}

    tl = str(data.get("trafficLight", "yellow")).lower()
    if tl not in {"green", "yellow", "red"}:
        tl = "yellow"

    log.info(f"Suggestions for {tl}: {data}")
    dt = time.perf_counter() - t0
    return {
        "suggestions": data.get("suggestions", []),
        "trafficLight": {"response": tl},
        "durations": {"total": dt},
    }
