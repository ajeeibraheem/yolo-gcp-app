from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])

@router.get("/healthz")
async def healthz():
    return {"ok": True}
