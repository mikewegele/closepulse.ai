import json
import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Header

from backend.agents_registration import runner, main_agent, traffic_light_agent, combo_agent
from backend.config import settings
from ..schemas import ChatMessage, AnalyzeResponse
from ..utils import system_date_message, with_timeout

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
        messages: List[ChatMessage],
        x_conversation_id: Optional[str] = Header(default=None, convert_underscores=False),
):
    t0 = time.perf_counter()
    try:
        payload = [m.dict() for m in messages] + [system_date_message()]
        ask_task = with_timeout(runner.run(main_agent, payload), timeout=settings.ASK_TIMEOUT, label="ask")
        tl_task = with_timeout(runner.run(traffic_light_agent, payload), timeout=settings.TL_TIMEOUT,
                               label="trafficLight")

        ask_res, tl_res = await asyncio.gather(ask_task, tl_task)  # type: ignore

        dt = time.perf_counter() - t0
        suggestions = getattr(ask_res, "final_output", None)
        tl_value = getattr(tl_res, "final_output", "yellow")

        return {
            "suggestions": suggestions,
            "trafficLight": {"response": tl_value},
            "durations": {"total": dt},
            "conversation_id": x_conversation_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analyze failed: {e}") from e


@router.post("/analyze_fast", response_model=AnalyzeResponse)
async def analyze_fast(
        messages: List[ChatMessage],
        x_conversation_id: Optional[str] = Header(default=None, convert_underscores=False),
):
    t0 = time.perf_counter()
    try:
        short = messages[-6:] if len(messages) > 6 else messages
        payload = [m.dict() for m in short] + [system_date_message()]

        res = await with_timeout(runner.run(combo_agent, payload), timeout=min(settings.ASK_TIMEOUT, 12),
                                 label="analyze_fast")
        raw = getattr(res, "final_output", "") or "{}"
        data = json.loads(raw)

        tl = str(data.get("trafficLight", "yellow")).lower()
        if tl not in ("green", "yellow", "red"):
            tl = "yellow"

        dt = time.perf_counter() - t0
        return {
            "suggestions": data.get("suggestions", []),
            "trafficLight": {"response": tl},
            "durations": {"total": dt},
            "conversation_id": x_conversation_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analyze_fast failed: {e}") from e
