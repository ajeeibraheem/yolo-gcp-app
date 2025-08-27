from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from . import indexes
from ..config import settings
import asyncio

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None

async def connect() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is not None:
        return _db
    _client = AsyncIOMotorClient(settings.MONGO_URI)
    _db = _client[settings.MONGO_DB]
    # Ensure indexes after DB is ready
    await indexes.ensure_indexes(_db)
    return _db

async def get_db() -> AsyncIOMotorDatabase:
    while _db is None:
        await asyncio.sleep(0.05)
    return _db  # type: ignore

async def close():
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
