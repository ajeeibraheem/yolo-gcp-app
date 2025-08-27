from typing import Optional
from google.cloud import storage
from ..config import settings
from uuid import uuid4
def _client() -> storage.Client:
    return storage.Client(project=settings.GCP_PROJECT_ID)
def _bucket():
    return _client().bucket(settings.GCS_BUCKET)
def new_object_name(dataset_name: str, relpath: str | None = None) -> str:
    base = f"uploads/{dataset_name}/{uuid4()}"
    return f"{base}/{relpath.lstrip('/')}" if relpath else base
def start_resumable_session(object_name: str, content_type: str, origin: Optional[str] = None) -> str:
    blob = _bucket().blob(object_name)
    return blob.create_resumable_upload_session(content_type=content_type, origin=origin)
