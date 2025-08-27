from __future__ import annotations
import os, tempfile, zipfile, mimetypes, re
from uuid import uuid4
from typing import Iterable, Tuple
from google.cloud import storage

# File types we care about
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
LABEL_EXTS = {".txt"}  # YOLO labels

def is_zip_uri(uri: str) -> bool:
    return uri.lower().endswith(".zip")

def _ctype_for(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "application/octet-stream"

def _split_gs(gcs_uri: str) -> Tuple[str, str]:
    assert gcs_uri.startswith("gs://"), f"not a gs:// URI: {gcs_uri}"
    rest = gcs_uri[5:]
    if "/" in rest:
        bucket, key = rest.split("/", 1)
    else:
        bucket, key = rest, ""
    return bucket, key

def _safe_rel(prefix: str, name: str) -> str:
    """Return a *relative* path for blob `name` under `prefix`."""
    rel = name[len(prefix):] if prefix else name
    rel = rel.replace("\\", "/")
    while rel.startswith("/"):  # guard absolute
        rel = rel[1:]
    rel = os.path.normpath(rel).replace("\\", "/")
    # block traversal / empty
    if not rel or rel.startswith(".."):
        return ""
    return rel

def download_gcs_uri(gcs_uri: str) -> str:
    """
    Download a GCS ZIP / single object / folder into a temp dir.
    For folders, also extracts any *.zip inside the prefix into that temp dir.
    Returns the local directory path containing the data.
    """
    client = storage.Client()
    bucket_name, key = _split_gs(gcs_uri)
    bucket = client.bucket(bucket_name)

    # --- ZIP passed directly ---
    if is_zip_uri(gcs_uri):
        fd, tmpzip = tempfile.mkstemp(suffix=".zip"); os.close(fd)
        try:
            bucket.blob(key).download_to_filename(tmpzip)
            out_dir = tempfile.mkdtemp(prefix="yolozip_")
            with zipfile.ZipFile(tmpzip) as z:
                z.extractall(out_dir)
            return out_dir
        finally:
            try: os.remove(tmpzip)
            except FileNotFoundError: pass

    # --- Single object (non-zip) ---
    if key and not gcs_uri.endswith("/"):
        blob = bucket.blob(key)
        if blob.exists():
            out_dir = tempfile.mkdtemp(prefix="yolosingle_")
            img_name = os.path.basename(key)
            dst = os.path.join(out_dir, "images", img_name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            blob.download_to_filename(dst)
            return out_dir
        # fall through if object doesn't exist

    # --- Prefix / folder ---
    prefix = key if not key else (key if key.endswith("/") else key + "/")
    out_dir = tempfile.mkdtemp(prefix="yolofolder_")

    zip_names, file_names = [], []
    for b in client.list_blobs(bucket_name, prefix=prefix):
        name = b.name
        if name.endswith("/"):
            continue
        rel = _safe_rel(prefix, name)
        if not rel:
            continue
        ext = os.path.splitext(rel.lower())[1]
        if ext == ".zip":
            zip_names.append(name)
        elif ext in (IMAGE_EXTS | LABEL_EXTS):
            file_names.append(name)

    # download images/labels directly
    for name in file_names:
        rel = _safe_rel(prefix, name)
        if not rel:
            continue
        dst = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        bucket.blob(name).download_to_filename(dst)

    # extract all zips we found into out_dir
    for name in zip_names:
        fd, tmpzip = tempfile.mkstemp(suffix=".zip"); os.close(fd)
        try:
            bucket.blob(name).download_to_filename(tmpzip)
            with zipfile.ZipFile(tmpzip) as z:
                z.extractall(out_dir)
        finally:
            try: os.remove(tmpzip)
            except FileNotFoundError: pass

    return out_dir

# --------- choose a destination in the same bucket for extracted files ---------

def _sanitize_segment(s: str) -> str:
    # safe for GCS path segments
    s = s.strip()
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s)
    return s.strip("-") or "dataset"

def derive_target_prefix(source_uri: str, dataset_name: str) -> str:
    """
    Choose a destination in the *same* bucket by default:
      gs://<bucket>/<EXTRACT_PREFIX_BASE>/<dataset_name>/<run_id>/
    Overrides:
      - GCS_BUCKET: force bucket
      - EXTRACT_PREFIX_BASE: top-level folder (default: "datasets")
      - EXTRACT_RUN_ID: fixed run id (default: random 12-char)
    """
    assert source_uri.startswith("gs://")
    bucket_from_src = source_uri.split("/", 3)[2]
    bucket = os.getenv("GCS_BUCKET", bucket_from_src)
    base = os.getenv("EXTRACT_PREFIX_BASE", "datasets").strip("/")
    run_id = os.getenv("EXTRACT_RUN_ID") or uuid4().hex[:12]
    ds = _sanitize_segment(dataset_name)
    return f"gs://{bucket}/{base}/{ds}/{run_id}/"

# --------- upload extracted directory back to GCS (images + labels) ---------

def upload_dir_to_gcs(
    local_dir: str,
    gs_prefix: str,
    *,
    include_exts: Iterable[str] | None = None,
) -> int:
    """
    Upload files from local_dir to gs_prefix, preserving relative paths.
    Default uploads images *and* YOLO label .txt so structure is complete.
    Returns number of uploaded files.
    """
    if not gs_prefix.endswith("/"):
        gs_prefix += "/"
    bucket_name, key_prefix = _split_gs(gs_prefix)
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    if include_exts is None:
        include_exts = IMAGE_EXTS | LABEL_EXTS  # upload images + labels

    uploaded = 0
    for root, _, files in os.walk(local_dir):
        for fn in files:
            ext = os.path.splitext(fn.lower())[1]
            if ext not in include_exts:
                continue
            lp = os.path.join(root, fn)
            rel = os.path.relpath(lp, local_dir).replace("\\", "/").lstrip("/")
            if not rel or rel.startswith(".."):
                continue
            name = key_prefix + rel
            blob = bucket.blob(name)
            blob.upload_from_filename(lp, content_type=_ctype_for(lp))
            uploaded += 1
    return uploaded
