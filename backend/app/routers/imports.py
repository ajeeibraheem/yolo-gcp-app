from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from typing import List
from ..services.uploads import start_resumable_session, new_object_name
from ..services.pubsub import publish_ingestion_message
from ..config import settings
router = APIRouter(prefix="/imports", tags=["imports"])
class ZipInitIn(BaseModel):
    dataset_name: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    content_type: str = "application/zip"
class ZipInitOut(BaseModel):
    upload_url: str; gcs_uri: str; object_name: str
class FileSpec(BaseModel): path: str; content_type: str
class FolderInitIn(BaseModel):
    dataset_name: str; files: List[FileSpec]
class BatchInitOut(BaseModel):
    prefix: str; items: List[dict]
class CompleteIn(BaseModel):
    dataset_name: str; gcs_uri: str

@router.post("/zip/initiate", response_model=ZipInitOut)
async def initiate_zip_upload(body: ZipInitIn, request: Request):
    origin = request.headers.get("origin")
    object_name = new_object_name(body.dataset_name, body.filename)
    upload_url = start_resumable_session(object_name, body.content_type, origin=origin)
    return {"upload_url": upload_url, "gcs_uri": f"gs://{settings.GCS_BUCKET}/{object_name}", "object_name": object_name}

@router.post("/folder/initiate", response_model=BatchInitOut)
async def initiate_folder_upload(body: FolderInitIn, request: Request):
    origin = request.headers.get("origin")
    prefix_object = new_object_name(body.dataset_name)
    items = []
    for f in body.files:
        object_name = f"{prefix_object}/{f.path.lstrip('/')}"
        upload_url = start_resumable_session(object_name, f.content_type, origin=origin)
        items.append({"path": f.path, "upload_url": upload_url, "gcs_uri": f"gs://{settings.GCS_BUCKET}/{object_name}", "object_name": object_name})
    return {"prefix": f"gs://{settings.GCS_BUCKET}/{prefix_object}/", "items": items}

@router.post("/images/initiate", response_model=BatchInitOut)
async def initiate_images_upload(body: FolderInitIn, request: Request):
    return await initiate_folder_upload(body, request)

@router.post("/complete")
async def complete_import(body: CompleteIn):
    msg_id = publish_ingestion_message({"dataset_name": body.dataset_name, "gcs_uri": body.gcs_uri, "format": "yolo"})
    return {"status": "queued", "message_id": msg_id}
