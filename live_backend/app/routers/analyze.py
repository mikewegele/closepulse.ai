# app/routers/analyze.py
import asyncio
import json
import time
from typing import List, Optional, Union, Iterable

from fastapi import APIRouter, HTTPException, Header

from ..agents import runner, main_agent, traffic_light_agent, combo_agent
from ..config import settings
from ..schemas import AnalyzeResponse, ChatMessage
from ..utils import system_date_message, with_timeout

router = APIRouter()


# ---------- helpers ----------

def _coerce_messages(messages: Iterable[Union[ChatMessage, dict]]) -> List[dict]:
    out: List[dict] = []
    for m in messages:
        if hasattr(m, "dict"):
            out.append(m.dict())  # Pydantic ChatMessage
        elif isinstance(m, dict):
            out.append(m)  # plain dict {"role": "...", "content": "..."}
        else:
            raise TypeError(f"Unsupported message type: {type(m)}")
    return out


async def _run_combo(payload: List[dict], timeout: float) -> dict:
    """
    Führt combo_agent aus, parst das JSON und liefert ein dict:
    { "suggestions": list, "trafficLight": {"response": "green|yellow|red"} }
    """
    res = await with_timeout(
        runner.run(combo_agent, payload),
        timeout=timeout,
        label="analyze_fast",
    )
    raw = getattr(res, "final_output", "") or "{}"
    data = json.loads(raw)

    tl = str(data.get("trafficLight", "yellow")).lower()
    if tl not in ("green", "yellow", "red"):
        tl = "yellow"

    return {
        "suggestions": data.get("suggestions", []),
        "trafficLight": {"response": tl},
    }


# ---------- WS-freundliche Helper-API (für stream.py) ----------

async def analyze_fast_ws(messages: Iterable[Union[ChatMessage, dict]]) -> dict:
    """
    WS-sichere Variante: wirft KEINE HTTPException.
    Gibt bei Fehler ein dict mit {"error": "..."} zurück.
    """
    try:
        short = list(messages)
        if len(short) > 6:
            short = short[-6:]
        payload = _coerce_messages(short) + [system_date_message()]

        result = await _run_combo(payload, timeout=min(settings.ASK_TIMEOUT, 12))
        return result
    except Exception as e:
        return {"error": f"analyze_fast failed: {e}"}


# ---------- HTTP-Routen ----------

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
        messages: List[ChatMessage],
        x_conversation_id: Optional[str] = Header(default=None, convert_underscores=False),
):
    t0 = time.perf_counter()
    try:
        payload = _coerce_messages(messages) + [system_date_message()]
        ask_task = with_timeout(runner.run(main_agent, payload), timeout=settings.ASK_TIMEOUT, label="ask")
        tl_task = with_timeout(runner.run(traffic_light_agent, payload), timeout=settings.TL_TIMEOUT,
                               label="trafficLight")

        ask_res, tl_res = await asyncio.gather(ask_task, tl_task)  # type: ignore

        suggestions = getattr(ask_res, "final_output", None)
        tl_value = getattr(tl_res, "final_output", "yellow")
        if str(tl_value).lower() not in ("green", "yellow", "red"):
            tl_value = "yellow"

        dt = time.perf_counter() - t0
        return {
            "suggestions": suggestions,
            "trafficLight": {"response": str(tl_value).lower()},
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
        payload = _coerce_messages(short) + [system_date_message()]
        result = await _run_combo(payload, timeout=min(settings.ASK_TIMEOUT, 12))

        dt = time.perf_counter() - t0
        return {
            "suggestions": result.get("suggestions", []),
            "trafficLight": result.get("trafficLight", {"response": "yellow"}),
            "durations": {"total": dt},
            "conversation_id": x_conversation_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analyze_fast failed: {e}") from e
