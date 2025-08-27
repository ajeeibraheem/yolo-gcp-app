import os
from google.cloud import storage
from ..config import settings
def get_client() -> storage.Client:
    return storage.Client(project=os.getenv("GCP_PROJECT_ID"))
def get_bucket():
    return get_client().bucket(settings.GCS_BUCKET)
def get_blob(bucket_name: str, object_name: str):
    client = get_client()
    return client.bucket(bucket_name).blob(object_name)
