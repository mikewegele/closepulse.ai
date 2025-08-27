import time

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_get():
    return {"status": "ok", "time": time.time()}


@router.head("/health")
async def health_head():
    # HEAD hat keinen Body; Status 200 reicht
    return
