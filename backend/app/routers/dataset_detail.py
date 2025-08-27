from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Dict, Any
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..db.client import get_db

router = APIRouter(tags=["datasets"])

@router.get("/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    include_counts: bool = Query(False, description="include image count"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        oid = ObjectId(dataset_id)
    except Exception:
        raise HTTPException(404, "invalid id")

    d = await db.datasets.find_one({"_id": oid})
    if not d:
        raise HTTPException(404, "not found")

    d["_id"] = str(d["_id"])
    d["can_preview"] = bool(d.get("source_prefix"))

    if include_counts:
        # Support ObjectId and legacy string dataset_id in images collection
        total = await db.images.count_documents({"$or": [{"dataset_id": oid}, {"dataset_id": dataset_id}]})
        d["image_count"] = total

    return d
