# backend/app/services/pubsub.py
from google.cloud import pubsub_v1
from ..config import settings
import os, json

def _resolve_project_id() -> str | None:
    # prefer explicit setting; then common env vars used by ADC
    return (
        getattr(settings, "GCP_PROJECT_ID", None)
        or os.getenv("GCP_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCLOUD_PROJECT")
    )

PROJECT_ID = _resolve_project_id()
TOPIC_NAME = getattr(settings, "PUBSUB_TOPIC", None) or os.getenv("PUBSUB_TOPIC") or "ingestion-tasks"

if not PROJECT_ID:
    # Fail at import time with a clear message
    raise RuntimeError("GCP Project ID not set. Set env GCP_PROJECT_ID (or GOOGLE_CLOUD_PROJECT / GCLOUD_PROJECT).")

_publisher = pubsub_v1.PublisherClient()
_TOPIC_PATH = _publisher.topic_path(PROJECT_ID, TOPIC_NAME)

def publish_ingestion_message(payload: dict, attributes: dict | None = None) -> str:
    """
    Publish to Pub/Sub 'projects/<PROJECT_ID>/topics/<TOPIC_NAME>'.
    Returns the server-assigned message ID.
    """
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    attrs = attributes or {}
    future = _publisher.publish(_TOPIC_PATH, data=data, **attrs)
    return future.result(timeout=30)
