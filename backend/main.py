# backend/main.py
import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from io import BytesIO
from typing import List, Dict, Any, Optional

import openai
from agents import Runner
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from closepulse_agents import main_agent, traffic_light_agent, database_agent
from models import Base, Conversation, Message

# -------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

runner = Runner()
app = FastAPI(title="closepulse.ai backend", version="1.4.0")

ALLOWED_ORIGINS = os.getenv("CLOSEPULSE_CORS", "").split(",") if os.getenv("CLOSEPULSE_CORS") else [
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "app://-",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=512)

log = logging.getLogger("app")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# -------------------------------------------------------------------
# Database (Neon Postgres / SQLite)
# -------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./closepulse.db")
engine = create_async_engine(DATABASE_URL, echo=False, future=True, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# -------------------------------------------------------------------
# Schemas
# -------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class AskResponse(BaseModel):
    response: str
    duration: float
    conversation_id: Optional[str] = None


class TLResponse(BaseModel):
    response: Any
    duration: float
    conversation_id: Optional[str] = None


class AnalyzeResponse(BaseModel):
    suggestions: Any = Field(..., description="JSON-Array oder Modell-Output für Vorschläge")
    trafficLight: Dict[str, str]
    durations: Dict[str, float]
    conversation_id: Optional[str] = None


# -------------------------------------------------------------------
# Utils
# -------------------------------------------------------------------
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


def safe_mime_from_upload(file: UploadFile) -> str:
    return file.content_type or "application/octet-stream"


async def get_or_create_conversation(db: AsyncSession, conversation_id: Optional[str]) -> str:
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
    conv = await db.get(Conversation, conversation_id)
    if not conv:
        conv = Conversation(id=conversation_id, started_at=now_berlin(), meta={})
        db.add(conv)
        await db.commit()
    return conversation_id


async def add_message(
        db: AsyncSession,
        conversation_id: str,
        role: str,
        content: str,
        source: Optional[str] = None,
        meta: Optional[dict] = None,
):
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        source=source,
        created_at=now_berlin(),
        meta=meta or {},
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def update_message_tl(
        db: AsyncSession,
        message_id: int,
        traffic_light: Optional[str],
):
    await db.execute(
        sa_update(Message)
        .where(Message.id == message_id)
        .values(traffic_light=traffic_light)
    )
    await db.commit()


# -------------------------------------------------------------------
# Health
# -------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "time": time.time()}


# -------------------------------------------------------------------
# Transcribe (EINZIGE Persistenz-Stelle)
# -------------------------------------------------------------------
@app.post("/transcribe")
async def transcribe(
        request: Request,
        file: UploadFile = File(...),
        x_conversation_id: Optional[str] = Header(default=None, convert_underscores=False),
):
    t0 = time.perf_counter()
    try:
        # Datei laden
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty audio payload")

        # Meta bestimmen
        mime = safe_mime_from_upload(file)
        name = file.filename or ("audio.webm" if "webm" in mime else "audio.wav")
        wav_io = BytesIO(raw)

        # Transkription
        transcription = openai.audio.transcriptions.create(
            file=(name, wav_io, mime),
            model=os.getenv("TRANSCRIBE_MODEL", "whisper-1"),
            language=os.getenv("TRANSCRIBE_LANG", "de"),
        )

        dt = time.perf_counter() - t0
        text = (getattr(transcription, "text", "") or "").strip()
        conversation_id = None

        anonym_text = ""
        if text:
            # DSGVO: Text über DatabaseAgent anonymisieren (1:1, nur PII maskieren)
            try:
                da_out = await runner.run(database_agent, [{"role": "user", "content": text}])
                anonym_text = (getattr(da_out, "final_output", "") or "").strip()
            except Exception:
                # Fallback: lieber nichts speichern als nicht-anonymisiert
                anonym_text = ""

            async with SessionLocal() as db:
                conversation_id = await get_or_create_conversation(db, x_conversation_id)

                if anonym_text:
                    await add_message(
                        db,
                        conversation_id,
                        role="user",
                        content=anonym_text,
                        source="transcribe",
                        meta={"mime": mime, "filename": name, "latency": dt},
                    )
                else:
                    # nichts speichern (sicherer Fallback)
                    pass

        print(f"/transcribe {dt:.3f}s")
        return {
            "text": text,
            "duration": dt,
            "conversation_id": conversation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        log.exception("transcribe failed: %s", e)
        raise HTTPException(status_code=500, detail=f"transcribe failed: {e}") from e


# -------------------------------------------------------------------
# Delete-Endpoint (DGSVO)
# -------------------------------------------------------------------
@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    # Optional: DatabaseAgent fragen (Policy zentral)
    payload = {"event": "DELETE_REQUEST", "conversation_id": conversation_id}
    db_decision = await runner.run(database_agent, [{"role": "user", "content": json.dumps(payload)}])
    action = json.loads(db_decision.final_output)
    if action.get("op") != "DELETE_CONVERSATION":
        return {"status": "skipped"}
    async with SessionLocal() as db:
        from sqlalchemy import delete
        await db.execute(delete(Message).where(Message.conversation_id == conversation_id))
        await db.execute(delete(Conversation).where(Conversation.id == conversation_id))
        await db.commit()
    return {"status": "deleted", "conversation_id": conversation_id}


# -------------------------------------------------------------------
# Read-Usecases (Export)
# -------------------------------------------------------------------
@app.get("/conversations/{conversation_id}/export")
async def export_conversation(conversation_id: str):
    # Agent kann Limit/Filter entscheiden; hier simpel:
    payload = {"event": "EXPORT", "conversation_id": conversation_id}
    db_decision = await runner.run(database_agent, [{"role": "user", "content": json.dumps(payload)}])
    action = json.loads(db_decision.final_output)
    if action.get("op") not in ("EXPORT_CONVERSATION", "LIST_MESSAGES"):
        action = {"op": "EXPORT_CONVERSATION", "data": {"conversation_id": conversation_id}}
    async with SessionLocal() as db:
        res = await db.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
        )
        msgs = res.scalars().all()
        return {
            "conversation_id": conversation_id,
            "messages": [
                {
                    "role": m.role,
                    "text": m.content,
                    "ts": m.created_at.isoformat(),
                    "traffic_light": m.traffic_light,
                }
                for m in msgs
            ],
        }


# -------------------------------------------------------------------
# Ask — KEINE Persistenz
# -------------------------------------------------------------------
@app.post("/ask", response_model=AskResponse)
async def ask_agent(
        messages: List[ChatMessage],
        x_conversation_id: Optional[str] = Header(default=None, convert_underscores=False),
):
    t0 = time.perf_counter()
    try:
        payload = [m.dict() for m in messages] + [system_date_message()]
        result = await with_timeout(
            runner.run(main_agent, payload),
            timeout=float(os.getenv("ASK_TIMEOUT", "25")),
            label="ask",
        )
        dt = time.perf_counter() - t0
        resp_text = result.final_output
        # Nichts speichern – nur zurückgeben
        print(f"/ask {dt:.3f}s (no storage)")
        return {"response": resp_text, "duration": dt, "conversation_id": x_conversation_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ask failed: {e}") from e


# -------------------------------------------------------------------
# Traffic Light — PERSISTENZ am letzten User-Message-Eintrag (nur Farbe)
# -------------------------------------------------------------------
@app.post("/trafficLight", response_model=TLResponse)
async def traffic_light(
        messages: List[ChatMessage],
        x_conversation_id: Optional[str] = Header(default=None, convert_underscores=False),
):
    t0 = time.perf_counter()
    try:
        payload = [m.dict() for m in messages] + [system_date_message()]
        result = await with_timeout(
            runner.run(traffic_light_agent, payload),
            timeout=float(os.getenv("TL_TIMEOUT", "15")),
            label="trafficLight",
        )
        dt = time.perf_counter() - t0
        tl_raw = getattr(result, "final_output", None)
        print(f"/trafficLight {dt:.3f}s | {tl_raw})")
        return {"response": tl_raw, "duration": dt, "conversation_id": x_conversation_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"trafficLight failed: {e}") from e


# -------------------------------------------------------------------
# Analyze (kombiniert) — KEINE Persistenz
# -------------------------------------------------------------------
@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
        messages: List[ChatMessage],
        request: Request,
        x_conversation_id: Optional[str] = Header(default=None, convert_underscores=False),
):
    t0 = time.perf_counter()
    try:
        payload = [m.dict() for m in messages] + [system_date_message()]
        ask_task = asyncio.create_task(
            with_timeout(runner.run(main_agent, payload), timeout=float(os.getenv("ASK_TIMEOUT", "25")), label="ask")
        )
        tl_task = asyncio.create_task(
            with_timeout(runner.run(traffic_light_agent, payload), timeout=float(os.getenv("TL_TIMEOUT", "15")),
                         label="trafficLight")
        )
        ask_res, tl_res = await asyncio.gather(ask_task, tl_task)

        dt = time.perf_counter() - t0
        suggestions = getattr(ask_res, "final_output", None)
        tl_value = getattr(tl_res, "final_output", "yellow")

        # Nichts speichern – nur zurückgeben
        print(f"/analyze {dt:.3f}s (no storage)")
        return {
            "suggestions": suggestions,
            "trafficLight": {"response": tl_value},
            "durations": {"total": dt},
            "conversation_id": x_conversation_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analyze failed: {e}") from e


# -------------------------------------------------------------------
# Read APIs (nur zum Auslesen der gespeicherten Transkripte)
# -------------------------------------------------------------------
class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    source: Optional[str]
    created_at: datetime
    meta: dict
    traffic_light: Optional[str] = None


class ConversationOut(BaseModel):
    id: str
    started_at: datetime
    meta: dict


@app.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(conversation_id: str):
    async with SessionLocal() as db:
        conv = await db.get(Conversation, conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return ConversationOut(id=conv.id, started_at=conv.started_at, meta=conv.meta)


@app.get("/conversations/{conversation_id}/messages", response_model=List[MessageOut])
async def list_messages(conversation_id: str):
    async with SessionLocal() as db:
        res = await db.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
        )
        msgs = res.scalars().all()
        return [
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                source=m.source,
                created_at=m.created_at,
                meta=m.meta,
                traffic_light=m.traffic_light,
            )
            for m in msgs
        ]
