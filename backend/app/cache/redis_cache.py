from __future__ import annotations
import os, json
from typing import Optional
from redis.asyncio import Redis

_client: Optional[Redis] = None
_PREFIX = os.getenv("CACHE_PREFIX", "yolo")

def _key(suffix: str) -> str:
    return f"{_PREFIX}:{suffix}"

def get_redis() -> Optional[Redis]:
    global _client
    url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    if not url:
        return None
    if _client is None:
        # decode_responses=False → bytes in/out (we handle JSON encoding)
        _client = Redis.from_url(url, decode_responses=False)
    return _client

async def get_json(suffix: str) -> Optional[dict]:
    r = get_redis()
    if not r: return None
    raw = await r.get(_key(suffix))
    if not raw: return None
    try:
        return json.loads(raw)
    except Exception:
        return None

async def set_json(suffix: str, value: dict, ttl: int) -> None:
    r = get_redis()
    if not r: return
    await r.set(_key(suffix), json.dumps(value).encode("utf-8"), ex=max(1, ttl))

async def get_bytes(suffix: str) -> Optional[bytes]:
    r = get_redis()
    if not r: return None
    return await r.get(_key(suffix))

async def set_bytes(suffix: str, value: bytes, ttl: int) -> None:
    r = get_redis()
    if not r: return
    await r.set(_key(suffix), value, ex=max(1, ttl))
