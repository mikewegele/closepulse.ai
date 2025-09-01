import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .routers import stream, transcribe, analyze


def create_app() -> FastAPI:
    app = FastAPI(title="ClosePulse Backend", version="1.0.0")
    allowed = os.getenv("CP_ALLOWED_ORIGINS")
    if allowed:
        allow_origins = [o.strip() for o in allowed.split(",") if o.strip()]
        allow_origin_regex = None
    else:
        allow_origins = []
        allow_origin_regex = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=512)
    app.include_router(stream.router, prefix="/local", tags=["stream"])
    app.include_router(transcribe.router, tags=["transcribe"])
    app.include_router(analyze.router, tags=["analyze"])
    return app
