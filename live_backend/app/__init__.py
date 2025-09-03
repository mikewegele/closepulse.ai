from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .routers import stream, transcribe, analyze, realtime


def create_app() -> FastAPI:
    app = FastAPI(title="ClosePulse Backend", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_origin_regex=None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=512)
    app.include_router(stream.router, prefix="/local", tags=["stream"])
    app.include_router(transcribe.router, tags=["transcribe"])
    app.include_router(analyze.router, tags=["analyze"])
    app.include_router(realtime.router, tags=["realtime"])
    return app
