from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..db.client import get_db

router = APIRouter(tags=["datasets"])

@router.get("/datasets")
async def list_datasets(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None, description="filter by dataset name (case-insensitive)"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    List datasets (paged). Returns minimal fields for UI table.
    Primary preview flag is presence of source_prefix (new worker flow).
    """
    match: Dict[str, Any] = {}
    if q:
        match["name"] = {"$regex": q, "$options": "i"}

    total = await db.datasets.count_documents(match)
    cursor = (
        db.datasets
        .find(match, {"name": 1, "created_at": 1, "updated_at": 1, "source_prefix": 1, "source_zip": 1})
        .sort("updated_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )

    items: List[Dict[str, Any]] = []
    async for d in cursor:
        d["_id"] = str(d["_id"])
        d["can_preview"] = bool(d.get("source_prefix"))
        items.append(d)

    return {"items": items, "page": page, "page_size": page_size, "total": total}
