from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import json, os
from google.cloud import pubsub_v1

router = APIRouter(tags=["ingestion"])

class IngestNow(BaseModel):
    dataset_name: str
    gcs_uri: Optional[str] = None
    gcs_uris: Optional[List[str]] = None
    format: str = "yolo"

def _topic() -> str:
    project = os.getenv("GCP_PROJECT_ID", "yolo-gcp-470119")
    topic = os.getenv("INGESTION_TOPIC", "ingestion-tasks")
    if not project:
        raise HTTPException(500, "GCP_PROJECT_ID not set")
    return f"projects/{project}/topics/{topic}"

@router.post("/ingestion/publish")
async def ingestion_publish(body: IngestNow):
    if not body.gcs_uri and not body.gcs_uris:
        raise HTTPException(400, "Provide gcs_uri or gcs_uris[]")

    msg = {"dataset_name": body.dataset_name, "format": body.format}
    if body.gcs_uris:
        msg["gcs_uris"] = body.gcs_uris
    else:
        msg["gcs_uri"] = body.gcs_uri

    pub = pubsub_v1.PublisherClient()
    try:
        future = pub.publish(_topic(), data=json.dumps(msg).encode("utf-8"))
        mid = future.result(timeout=30)
        return {"status": "ok", "message_id": mid}
    except Exception as e:
        raise HTTPException(500, f"Pub/Sub publish failed: {e}")
