# backend/main.py
import asyncio
import os
import time
from datetime import datetime
from io import BytesIO
from typing import List, Dict, Any

import openai
from agents import Runner
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field

from closepulse_agents import main_agent, traffic_light_agent

# -------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

runner = Runner()
app = FastAPI(title="closepulse.ai backend", version="1.1.0")

# Electron/Dev CORS: localhost + file/app protocols häufig in Electron
ALLOWED_ORIGINS = os.getenv("CLOSEPULSE_CORS", "").split(",") if os.getenv("CLOSEPULSE_CORS") else [
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    # wenn Electron eigenes Protokoll nutzt:
    "app://-",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# gzip spart IO-Zeit bei JSON-Responses
app.add_middleware(GZipMiddleware, minimum_size=512)


# -------------------------------------------------------------------
# Schemas
# -------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class AskResponse(BaseModel):
    response: str
    duration: float


class TLResponse(BaseModel):
    response: str
    duration: float


class AnalyzeResponse(BaseModel):
    suggestions: Any = Field(..., description="JSON-Array oder Modell-Output für Vorschläge")
    trafficLight: Dict[str, str]
    durations: Dict[str, float]


# -------------------------------------------------------------------
# Utils
# -------------------------------------------------------------------
def now_berlin_iso() -> str:
    # explizit Europe/Berlin
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo("Europe/Berlin")
        return datetime.now(tz=tz).date().isoformat()
    except Exception:
        return datetime.utcnow().date().isoformat()


def system_date_message() -> Dict[str, str]:
    return {"role": "system", "content": f"Heute ist der {now_berlin_iso()}"}


async def with_timeout(coro, timeout: float, label: str):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail=f"{label} timed out after {timeout}s")


def safe_mime_from_upload(file: UploadFile) -> str:
    # Whisper akzeptiert webm, wav, mp3, m4a etc. — wir verwenden, was geliefert wird
    return file.content_type or "application/octet-stream"


# -------------------------------------------------------------------
# Health
# -------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "time": time.time()}


# -------------------------------------------------------------------
# Transcribe
# -------------------------------------------------------------------
@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    t0 = time.perf_counter()
    try:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty audio payload")
        mime = safe_mime_from_upload(file)
        name = file.filename or ("audio.webm" if "webm" in mime else "audio.wav")

        # Wichtig: nicht fälschlich als WAV labeln, wenn es webm ist
        wav_io = BytesIO(raw)
        transcription = openai.audio.transcriptions.create(
            file=(name, wav_io, mime),
            model=os.getenv("TRANSCRIBE_MODEL", "whisper-1"),
            language=os.getenv("TRANSCRIBE_LANG", "de")
        )
        dt = time.perf_counter() - t0
        print(f"/transcribe {dt:.3f}s")
        return {"text": transcription.text, "duration": dt}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"transcribe failed: {e}") from e


# -------------------------------------------------------------------
# Ask (Suggestions)
# -------------------------------------------------------------------
@app.post("/ask", response_model=AskResponse)
async def ask_agent(messages: List[ChatMessage]):
    t0 = time.perf_counter()
    try:
        payload = [m.dict() for m in messages] + [system_date_message()]
        # Timeout begrenzen, damit Frontend nicht wartet
        result = await with_timeout(runner.run(main_agent, payload), timeout=float(os.getenv("ASK_TIMEOUT", "25")),
                                    label="ask")
        dt = time.perf_counter() - t0
        print(f"/ask {dt:.3f}s")
        return {"response": result.final_output, "duration": dt}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ask failed: {e}") from e


# -------------------------------------------------------------------
# Traffic Light
# -------------------------------------------------------------------
@app.post("/trafficLight", response_model=TLResponse)
async def traffic_light(messages: List[ChatMessage]):
    t0 = time.perf_counter()
    try:
        payload = [m.dict() for m in messages] + [system_date_message()]
        result = await with_timeout(
            runner.run(traffic_light_agent, payload),
            timeout=float(os.getenv("TL_TIMEOUT", "15")),
            label="trafficLight",
        )
        dt = time.perf_counter() - t0
        print(f"/trafficLight {dt:.3f}s")
        return {"response": result.final_output, "duration": dt}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"trafficLight failed: {e}") from e


# -------------------------------------------------------------------
# Analyze (kombinierter Endpoint: spart 1 Roundtrip)
# -------------------------------------------------------------------
@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(messages: List[ChatMessage], request: Request):
    t0 = time.perf_counter()
    try:
        payload = [m.dict() for m in messages] + [system_date_message()]

        # beide Agents parallel
        ask_task = asyncio.create_task(with_timeout(
            runner.run(main_agent, payload), timeout=float(os.getenv("ASK_TIMEOUT", "25")), label="ask"
        ))
        tl_task = asyncio.create_task(with_timeout(
            runner.run(traffic_light_agent, payload), timeout=float(os.getenv("TL_TIMEOUT", "15")), label="trafficLight"
        ))

        ask_res, tl_res = await asyncio.gather(ask_task, tl_task)

        dt = time.perf_counter() - t0
        print(f"/analyze {dt:.3f}s")
        return {
            "suggestions": getattr(ask_res, "final_output", None),
            "trafficLight": {"response": getattr(tl_res, "final_output", "yellow")},
            "durations": {
                "total": dt,
                "ask": getattr(ask_res, "duration", None) or 0.0,
                "trafficLight": getattr(tl_res, "duration", None) or 0.0,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analyze failed: {e}") from e
