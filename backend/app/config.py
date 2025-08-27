from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB: str = "yoloapp"

    GCP_PROJECT_ID: str = "yolo-gcp-470119"
    GCP_REGION: str = "us-central1"
    GCS_BUCKET: str = "yolo-datasets-yolo-gcp-470119"

    PUBSUB_TOPIC: str = "ingestion-tasks"
    PUBSUB_SUBSCRIPTION: str = "ingestion-sub"
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    AUTH_MODE: str = "DEV_NO_AUTH"

settings = Settings()
