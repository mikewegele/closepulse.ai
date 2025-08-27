from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .config import settings
from .db import init_models
from .logging import setup_logging
from .routers import health, transcribe, analyze

log = setup_logging()


def create_app() -> FastAPI:
    app = FastAPI(title="closepulse.ai backend", version="1.5.0")

    allowed = settings.CLOSEPULSE_CORS.split(",") if settings.CLOSEPULSE_CORS else [
        "http://localhost", "http://127.0.0.1",
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:8080", "http://127.0.0.1:8080",
        "app://-",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=512)

    @app.on_event("startup")
    async def startup():
        await init_models()

    app.include_router(health.router)
    app.include_router(transcribe.router)
    app.include_router(analyze.router)
    return app
