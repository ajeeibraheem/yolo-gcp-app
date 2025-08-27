from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from typing import Optional, Dict, Any, List, Tuple
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..db.client import get_db
from ..utils import parse_gs_uri
from ..services.gcs import get_blob
from ..cache.redis_cache import (
    get_json as cache_get_json,
    set_json as cache_set_json,
    get_bytes as cache_get_bytes,
    set_bytes as cache_set_bytes,
)

# GCS + misc
from google.cloud import storage
from datetime import datetime, timedelta, timezone
import mimetypes, tempfile, zipfile, os, hashlib, logging
import email.utils as eut
from urllib.parse import quote_plus

router = APIRouter(tags=["images"])
log = logging.getLogger(__name__)

# ------------ config knobs (env) ------------
IMG_BYTES_TTL   = int(os.getenv("CACHE_IMAGE_BYTES_TTL", "600"))           # 10 min
IMG_BYTES_MAX   = int(os.getenv("CACHE_IMAGE_BYTES_MAX", str(1024*1024)))   # 1 MiB
URL_DEFAULT_TTL = int(os.getenv("IMAGE_URL_TTL", "3600"))                   # 1 hour
URL_SAFETY      = int(os.getenv("SIGNED_URL_SAFETY", "60"))                 # shave a minute off cache
PREVIEW_BASE    = os.getenv("PREVIEW_PREFIX_BASE", "previews").strip("/")
GCS_OVERRIDE    = os.getenv("GCS_BUCKET")  # optional override bucket for zip-caches

# How to behave when signing isn't possible:
#   auto (default): try to sign, else fall back to proxy
#   proxy: always return proxy URLs (never sign)
#   signed-only: only signed URLs; return None (frontend should handle)
SIGNED_URLS_MODE = os.getenv("SIGNED_URLS_MODE", "proxy").lower().strip()
SAFETY_SECONDS = 30  # shave off a bit from TTL to avoid edge expiries

# ------------ small helpers ------------

def _norm(p: str) -> str:
    return (p or "").lstrip("/").replace("\\", "/")

def _httpdate(dt: datetime) -> str:
    return eut.format_datetime(dt.astimezone(timezone.utc), usegmt=True)

def _proxy_url(dataset_id: str, rel_path: str) -> str:
    return f"/datasets/{dataset_id}/image?path={quote_plus(_norm(rel_path))}"

def _blob_from_prefix(prefix_uri: str, rel_path: str):
    bucket, key_prefix = parse_gs_uri(prefix_uri)
    key_prefix = (key_prefix or "").rstrip("/")
    object_name = f"{key_prefix}/{_norm(rel_path)}" if key_prefix else _norm(rel_path)
    return bucket, object_name, get_blob(bucket, object_name)

def _gcs_meta(blob):
    blob.reload()
    etag = blob.etag
    updated = blob.updated or datetime.now(timezone.utc)
    ctype = blob.content_type or "application/octet-stream"
    size = int(blob.size or 0)
    return etag, updated, ctype, size

def _maybe_304(request: Request, etag: str | None, updated: datetime | None):
    inm = request.headers.get("if-none-match")
    ims = request.headers.get("if-modified-since")
    if etag and inm and inm.strip() == etag:
        return Response(status_code=304)
    if updated and ims:
        try:
            ims_dt = eut.parsedate_to_datetime(ims)
            if ims_dt and updated <= ims_dt:
                return Response(status_code=304)
        except Exception:
            pass
    return None

def _add_cache_headers(resp: Response, *, etag: str | None, updated: datetime | None, ctype: str, size: int):
    if etag:   resp.headers["ETag"] = etag
    if updated:resp.headers["Last-Modified"] = _httpdate(updated)
    resp.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=600"
    if size:   resp.headers["Content-Length"] = str(size)
    resp.media_type = ctype

def _zip_cache_bucket_and_key(dataset_doc: dict, rel_path: str) -> Tuple[str, str]:
    rel_path = _norm(rel_path)
    if GCS_OVERRIDE:
        bucket = GCS_OVERRIDE
    else:
        if not dataset_doc.get("source_zip"):
            raise RuntimeError("Cannot derive cache bucket without source_zip")
        bucket, _ = parse_gs_uri(dataset_doc["source_zip"])
    dataset_id = str(dataset_doc["_id"])
    name = f"{PREVIEW_BASE}/{dataset_id}/{rel_path}"
    return bucket, name

def _ensure_cached_zip_blob(dataset_doc: dict, rel_path: str) -> Tuple[str, str]:
    rel_path = _norm(rel_path)
    src_zip = dataset_doc.get("source_zip")
    if not src_zip:
        raise HTTPException(400, "dataset missing source_zip")

    cache_bucket, cache_name = _zip_cache_bucket_and_key(dataset_doc, rel_path)
    client = storage.Client()
    cblob = client.bucket(cache_bucket).blob(cache_name)
    if cblob.exists():
        return cache_bucket, cache_name

    zip_bucket, zip_key = parse_gs_uri(src_zip)
    zblob = client.bucket(zip_bucket).blob(zip_key)
    if not zblob.exists():
        raise HTTPException(404, "ZIP object not found in GCS")

    with tempfile.NamedTemporaryFile(suffix=".zip") as tf:
        zblob.download_to_filename(tf.name)
        with zipfile.ZipFile(tf.name) as zf:
            target = rel_path
            try:
                data = zf.read(target)
            except KeyError:
                matches = [n for n in zf.namelist() if n.replace("\\", "/").endswith(rel_path)]
                if not matches:
                    raise HTTPException(404, f"image '{rel_path}' not found in ZIP")
                target = sorted(matches, key=len)[0]
                data = zf.read(target)

    ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
    cblob.upload_from_string(data, content_type=ctype)
    return cache_bucket, cache_name

def _sign_url(bucket: str, name: str, *, ttl_s: int, disposition: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Try to produce a V4 signed URL. On failure (e.g. local OAuth creds without private key),
    return (None, None). Caller decides to fall back to proxy depending on SIGNED_URLS_MODE.
    """
    try:
        client = storage.Client()
        blob = client.bucket(bucket).blob(name)
        if not blob.exists():
            raise HTTPException(404, "object not found in GCS")
        expires = datetime.now(timezone.utc) + timedelta(seconds=max(1, ttl_s - SAFETY_SECONDS))
        params = {"version": "v4", "expiration": expires, "method": "GET"}
        if disposition:
            params["response_disposition"] = disposition
        url = blob.generate_signed_url(**params)
        return url, expires.replace(microsecond=0).isoformat() + "Z"
    except Exception as e:
    # Avoid reserved LogRecord attribute names like "name", "msg", etc.
        log.warning(
            "signed_url.failed",
            extra={
                "ctx_bucket": bucket,
                "ctx_blob_name": name,
                "ctx_reason": type(e).__name__,
            },
        )
        return None, None


def _disp_for_download(as_download: bool, rel_path: str, filename: Optional[str]) -> Optional[str]:
    if not as_download:
        return None
    disp_name = filename or os.path.basename(rel_path) or "download"
    return f'attachment; filename="{disp_name}"'

def _hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


@router.get("/datasets/{dataset_id}/images")
async def list_images(
    dataset_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=200),
    q: Optional[str] = Query(None, description="filename contains (case-insensitive)"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        oid = ObjectId(dataset_id)
    except Exception:
        raise HTTPException(404, "invalid id")

    match: Dict[str, Any] = {"$or": [{"dataset_id": oid}, {"dataset_id": dataset_id}]}
    if q:
        match["image_path"] = {"$regex": q, "$options": "i"}

    total = await db.images.count_documents(match)
    cursor = (
        db.images
        .find(match, {"_id": 0, "image_path": 1, "labels": 1, "dataset_id": 1})
        .sort("image_path", 1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )

    items: List[Dict[str, Any]] = []
    async for doc in cursor:
        if isinstance(doc.get("dataset_id"), ObjectId):
            doc["dataset_id"] = str(doc["dataset_id"])
        items.append(doc)

    return {"items": items, "page": page, "page_size": page_size, "total": total}

# --------- BYTES (proxy) with Redis cache for small images ---------

@router.get("/datasets/{dataset_id}/image")
async def get_image_bytes(
    dataset_id: str,
    path: str = Query(..., description="relative image path within dataset"),
    request: Request = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        oid = ObjectId(dataset_id)
    except Exception:
        raise HTTPException(404, "invalid id")
    d = await db.datasets.find_one({"_id": oid})
    if not d:
        raise HTTPException(404, "dataset not found")

    rel = _norm(path)

    # primary: prefix
    if d.get("source_prefix"):
        bucket, name, blob = _blob_from_prefix(d["source_prefix"], rel)
    elif d.get("source_zip"):
        bucket, name = _ensure_cached_zip_blob(d, rel)
        blob = storage.Client().bucket(bucket).blob(name)
    else:
        raise HTTPException(400, "dataset has neither source_prefix nor source_zip")

    if not blob.exists():
        raise HTTPException(404, "object not found in GCS")

    etag, updated, ctype, size = _gcs_meta(blob)

    # client cache validation
    pre = _maybe_304(request, etag, updated)
    if pre:
        return pre

    # server-side Redis cache for small images
    cache_key = f"img:{bucket}:{name}:{etag}"
    data: Optional[bytes] = None
    if size and size <= IMG_BYTES_MAX:
        data = await cache_get_bytes(cache_key)
        if data is None:
            data = blob.download_as_bytes()
            await cache_set_bytes(cache_key, data, IMG_BYTES_TTL)
    else:
        data = blob.download_as_bytes()

    resp = Response(content=data)
    _add_cache_headers(resp, etag=etag, updated=updated, ctype=ctype, size=len(data))
    return resp

# --------- SINGLE signed URL (with fallback) ---------

@router.get("/datasets/{dataset_id}/image-url")
async def get_image_signed_url(
    dataset_id: str,
    path: str = Query(..., description="relative image path within dataset"),
    ttl: int = Query(default=URL_DEFAULT_TTL, ge=60, le=60*60*24),
    as_download: bool = Query(False),
    filename: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    try:
        oid = ObjectId(dataset_id)
    except Exception:
        raise HTTPException(404, "invalid id")
    d = await db.datasets.find_one({"_id": oid})
    if not d:
        raise HTTPException(404, "dataset not found")

    rel = _norm(path)

    if d.get("source_prefix"):
        bucket, prefix = parse_gs_uri(d["source_prefix"])
        key_prefix = (prefix or "").rstrip("/")
        name = f"{key_prefix}/{rel}" if key_prefix else rel
    elif d.get("source_zip"):
        bucket, name = _ensure_cached_zip_blob(d, rel)
    else:
        raise HTTPException(400, "dataset has neither source_prefix nor source_zip")

    # optional signing (or proxy)
    if SIGNED_URLS_MODE != "proxy":
        blob = storage.Client().bucket(bucket).blob(name)
        if not blob.exists():
            raise HTTPException(404, "object not found in GCS")
        etag, _, _, _ = _gcs_meta(blob)

        disp = _disp_for_download(as_download, rel, filename)
        disp_hash = _hash(disp or "")
        ttl_eff = max(60, ttl - URL_SAFETY)
        ckey = f"url:{bucket}:{name}:{etag}:{ttl}:{disp_hash}"

        cached = await cache_get_json(ckey)
        if cached and "url" in cached and "expires_at" in cached:
            return cached

        url, expires_at = _sign_url(bucket, name, ttl_s=ttl, disposition=disp)
        if url:
            payload = {"url": url, "expires_at": expires_at, "bucket": bucket, "name": name}
            await cache_set_json(ckey, payload, ttl_eff)
            return payload

        # signing failed
        if SIGNED_URLS_MODE == "signed-only":
            return {"url": None, "expires_at": None, "bucket": bucket, "name": name}

    # proxy fallback
    return {"url": _proxy_url(dataset_id, rel), "expires_at": None, "bucket": bucket, "name": name}

# --------- BATCH signed URLs for a page (with fallback) ---------

@router.get("/datasets/{dataset_id}/image-urls")
async def get_image_signed_urls_batch(
    dataset_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=200),
    q: Optional[str] = Query(None, description="filename contains"),
    ttl: int = Query(default=URL_DEFAULT_TTL, ge=60, le=60*60*24),
    as_download: bool = Query(False),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns signed (or proxy) URLs for all images on the requested page.
    Response: { items: [{image_path, url, expires_at}], page, page_size, total }
    """
    try:
        oid = ObjectId(dataset_id)
    except Exception:
        raise HTTPException(404, "invalid id")
    d = await db.datasets.find_one({"_id": oid})
    if not d:
        raise HTTPException(404, "dataset not found")

    # fetch the page of images (no labels by default for speed)
    match: Dict[str, Any] = {"$or": [{"dataset_id": oid}, {"dataset_id": dataset_id}]}
    if q:
        match["image_path"] = {"$regex": q, "$options": "i"}

    total = await db.images.count_documents(match)
    cursor = (
        db.images
        .find(match, {"_id": 0, "image_path": 1})
        .sort("image_path", 1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    paths: List[str] = []
    async for doc in cursor:
        paths.append(doc["image_path"])

    client = storage.Client()
    disp_hash = _hash(_disp_for_download(as_download, "", None) or "")
    ttl_eff = max(60, ttl - URL_SAFETY)

    async def sign_for(rel: str) -> Dict[str, Any]:
        reln = _norm(rel)

        # resolve bucket/name
        if d.get("source_prefix"):
            bkt, prefix = parse_gs_uri(d["source_prefix"])
            kp = (prefix or "").rstrip("/")
            name = f"{kp}/{reln}" if kp else reln
            bucket = bkt
        elif d.get("source_zip"):
            bucket, name = _ensure_cached_zip_blob(d, reln)
        else:
            # shouldn't happen given earlier branch
            return {"image_path": rel, "url": _proxy_url(dataset_id, reln), "expires_at": None}

        # Signing path
        if SIGNED_URLS_MODE != "proxy":
            blob = client.bucket(bucket).blob(name)
            if blob.exists():
                etag, _, _, _ = _gcs_meta(blob)
                ckey = f"url:{bucket}:{name}:{etag}:{ttl}:{disp_hash}"
                cached = await cache_get_json(ckey)
                if cached:
                    return {"image_path": rel, **cached}

                url, expires_at = _sign_url(bucket, name, ttl_s=ttl,
                                            disposition=_disp_for_download(as_download, reln, None))
                if url:
                    payload = {"url": url, "expires_at": expires_at, "bucket": bucket, "name": name}
                    await cache_set_json(ckey, payload, ttl_eff)
                    return {"image_path": rel, **payload}

                if SIGNED_URLS_MODE == "signed-only":
                    return {"image_path": rel, "url": None, "expires_at": None}

        # Proxy fallback
        return {"image_path": rel, "url": _proxy_url(dataset_id, reln), "expires_at": None}

    # Sequential is fine for <= 90 items; keeps GCS IAM signing pressure low
    items = [await sign_for(p) for p in paths]

    return {"items": items, "page": page, "page_size": page_size, "total": total}
