from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .config import settings
from .db import init_models
from .logging import setup_logging
from .routers import telnyx_incoming, telnyx_stream, ws, transcribe, analyze, suggest, audio

log = setup_logging()


def create_app() -> FastAPI:
    app = FastAPI(title="closepulse.ai backend", version="1.5.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://api.closepulse192.win", "http://localhost:8000", "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=512)

    app.include_router(telnyx_incoming.router)
    app.include_router(telnyx_stream.router)
    app.include_router(ws.router)
    app.include_router(transcribe.router)
    app.include_router(analyze.router)
    app.include_router(suggest.router)
    app.include_router(audio.router)

    @app.on_event("startup")
    async def _startup():
        await init_models()

    return app
