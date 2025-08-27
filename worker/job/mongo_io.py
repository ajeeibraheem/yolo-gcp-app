from __future__ import annotations
import os, re
from datetime import datetime
from typing import Any, Dict, List, Iterable
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import UpdateOne, ASCENDING

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None

def _redact(uri: str) -> str:
    # hide password in logs if you ever print this
    return re.sub(r'//([^:/]+):([^@]+)@', r'//\1:****@', uri or '')

async def get_db() -> AsyncIOMotorDatabase:
    """Create a singleton Motor DB client; fail fast if not reachable."""
    global _client, _db
    if _db is not None:
        return _db
    uri = os.getenv("MONGO_URI")
    dbname = os.getenv("MONGO_DB")
    if not uri or not dbname:
        raise RuntimeError("MONGO_URI and/or MONGO_DB not set")
    _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    # Fail fast if server not reachable
    await _client.admin.command("ping")
    _db = _client[dbname]
    return _db

def _utcnow() -> datetime:
    return datetime.utcnow()

async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    images = db.images
    desired = [("dataset_id", ASCENDING), ("image_path", ASCENDING)]
    existing = await images.index_information()

    def is_equivalent(spec: dict) -> bool:
        keys = spec.get("key") or spec.get("keyPattern")
        return list(keys) == desired and bool(spec.get("unique"))

    if not any(is_equivalent(spec) for spec in existing.values()):
        await images.create_index(desired, name="uq_image_path_per_dataset", unique=True, background=True)

    if not any(spec.get("key") == [("dataset_id", 1)] for spec in existing.values()):
        await images.create_index([("dataset_id", ASCENDING)], name="ix_images_dataset_id", background=True)

    if not any(spec.get("key") == [("image_path", 1)] for spec in existing.values()):
        await images.create_index([("image_path", ASCENDING)], name="ix_images_image_path", background=True)

async def upsert_dataset(name: str, source_uri: str | None = None) -> str:
    """
    Create/update a dataset document and record its source:
      - *.zip   -> source_zip
      - gs://.../prefix/ -> source_prefix
      - gs://.../file.jpg -> source_prefix = parent folder
    """
    db = await get_db()
    update: Dict[str, Any] = {
        "$setOnInsert": {"name": name, "created_at": _utcnow()},
        "$set": {"updated_at": _utcnow()},
    }
    if source_uri and source_uri.startswith("gs://"):
        if source_uri.lower().endswith(".zip"):
            update["$set"]["source_zip"] = source_uri
            update.setdefault("$unset", {}).update({"source_prefix": ""})
        else:
            # derive prefix
            prefix = source_uri if source_uri.endswith("/") else source_uri.rsplit("/", 1)[0] + "/"
            update["$set"]["source_prefix"] = prefix
            update.setdefault("$unset", {}).update({"source_zip": ""})

    await db.datasets.update_one({"name": name}, update, upsert=True)
    doc = await db.datasets.find_one({"name": name}, {"_id": 1})
    return str(doc["_id"])

def _coalesce_path(d: Dict[str, Any]) -> str | None:
    """Accept multiple possible keys from parsers: image_path | path | file | filename."""
    return d.get("image_path") or d.get("path") or d.get("file") or d.get("filename")

async def bulk_upsert_images(dataset_id: str, docs: List[Dict[str, Any]]) -> int:
    """
    Upsert image records with labels.
    Ensures unique (dataset_id, image_path) so re-ingestion is idempotent.
    Returns number of processed images.
    """
    db = await get_db()
    await ensure_indexes(db)

    images = db.images
    oid = ObjectId(dataset_id)
    now = _utcnow()

    ops: List[UpdateOne] = []
    seen: set[str] = set()

    for d in docs:
        path = _coalesce_path(d)
        if not path:
            continue
        # dedupe within this batch
        if path in seen:
            continue
        seen.add(path)
        labels = d.get("labels", [])
        ops.append(
            UpdateOne(
                {"dataset_id": oid, "image_path": path},
                {
                    "$setOnInsert": {"dataset_id": oid, "image_path": path, "created_at": now},
                    "$set": {"labels": labels, "updated_at": now},
                },
                upsert=True,
            )
        )

    if not ops:
        return 0

    # Chunk to keep batches reasonable
    CHUNK = 1000
    total_processed = 0
    for i in range(0, len(ops), CHUNK):
        res = await images.bulk_write(ops[i : i + CHUNK], ordered=False)
        # Count how many docs we touched (approximate equals len(chunk))
        total_processed += (res.upserted_count or 0) + (res.modified_count or 0)
        # If neither modified nor upserted were reported (e.g., same content), still count them
        if total_processed == 0:
            total_processed = len(ops)

    return max(total_processed, len(seen))
